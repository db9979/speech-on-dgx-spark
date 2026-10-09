// Spark: voice assistant on the watch. SELECT asks (dictation via the phone), the phone
// fetches the answer from the DGX Spark and sends text plus 8 kHz IMA ADPCM audio,
// which plays on the watch speaker.
#include <pebble.h>
#include "face.h"

#define ANSWER_MAX 3000
#define RING_SIZE 16384        // ADPCM bytes: 4 s of speech
#define PREBUFFER 6000         // start playing after 1.5 s of audio (or at the end)
#define REBUFFER 4000          // after the buffer ran dry: wait for 1 s more, plus 0.5 s per earlier stall
#define REBUFFER_MAX 12000
#define CREDIT_STEP 2048       // tell the phone about freed space in steps of this
#define DECODE_BYTES 128       // ADPCM bytes decoded per speaker write (256 samples)
#define MOUTH_DELAY 12          // audio ticks (40 ms) between decoding and hearing
#define PERSIST_SPEAK 1
#define PERSIST_VOLUME 2
#define PERSIST_AUTOLISTEN 3
#define PERSIST_FACE 4
#define ANSWER_TIMEOUT 30      // seconds without any message from the phone: give up
#define SEND_TRIES 6           // attempts for a message to the phone
#define FREED_EVERY 2          // seconds: repeat the buffer report (it may get lost)
#define INBOX_MAX 4096

static Window *s_window;
static Layer *s_face_layer;
static TextLayer *s_status_layer;
static ScrollLayer *s_scroll_layer;
static TextLayer *s_text_layer;
static DictationSession *s_dictation;

static char s_question[300];
static char s_answer[ANSWER_MAX];
static char s_body[ANSWER_MAX + 340];
static char s_status[64];

static bool s_speak = true;
static int s_volume = 100;
static bool s_autolisten = true;
static bool s_busy;            // an answer is being fetched
static int32_t s_seq;          // number of the current question; older messages are ignored
static bool s_expect_audio;    // the phone sends speech for this answer
static bool s_text_done;
static time_t s_last_rx;       // last message for this question
static time_t s_dict_start;
static int32_t s_dict_ms;
static AppTimer *s_watchdog;

// messages to the phone: one at a time, repeated when they fail
typedef enum { OutNone, OutQuestion, OutCancel, OutReset, OutFreed } OutKind;
static OutKind s_out;          // what is on its way right now
static bool s_q_pending, s_cancel_pending, s_reset_pending, s_freed_due;
static int32_t s_cancel_seq;
static int s_tries;
static AppTimer *s_retry;
static uint32_t s_inbox;

// audio
static uint8_t *s_ring;
static uint32_t s_head, s_tail, s_fill;
static bool s_rebuf;           // the buffer ran dry: wait until enough is back, one pause instead of stutter
static int32_t s_stalls;        // how often that happened in this answer (goes to the Spark log)
static bool s_audio_end, s_playing;
static uint32_t s_freed_total;  // ADPCM bytes played since the question (the phone sends at most this + RING_SIZE)
static uint32_t s_freed_sent;   // last value the phone confirmed
static uint32_t s_freed_out;    // value on its way
static int s_pred, s_index;
static int16_t s_pcm[DECODE_BYTES * 2];
static uint32_t s_pcm_len, s_pcm_off;   // bytes of s_pcm not yet accepted by the speaker
static AppTimer *s_timer;
static uint8_t s_levels[MOUTH_DELAY];  // loudness per tick, played out ~0.5 s later
static uint8_t s_level_pos, s_tick_level;

static const int16_t STEPS[89] = {
  7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66,
  73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408,
  449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
  2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630,
  9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767};
static const int8_t INDEX[8] = {-1, -1, -1, -1, 2, 4, 6, 8};

static void set_status(const char *text) {
  snprintf(s_status, sizeof(s_status), "%s", text);
  text_layer_set_text(s_status_layer, s_status);
}

static void update_text(void) {
  if (s_question[0]) {
    snprintf(s_body, sizeof(s_body), "» %s\n\n%s", s_question, s_answer);
  } else {
    snprintf(s_body, sizeof(s_body), "%s", s_answer[0] ? s_answer :
             "SELECT: Frage stellen\nlang SELECT: neues Gespräch");
  }
  text_layer_set_text(s_text_layer, s_body);
  GRect bounds = layer_get_bounds(scroll_layer_get_layer(s_scroll_layer));
  int width = bounds.size.w - PBL_IF_ROUND_ELSE(40, 8);
  text_layer_set_size(s_text_layer, GSize(width, 4000));  // measure without the old height's clipping
  GSize size = text_layer_get_content_size(s_text_layer);
  text_layer_set_size(s_text_layer, GSize(width, size.h + 10));
  scroll_layer_set_content_size(s_scroll_layer, GSize(bounds.size.w, size.h + PBL_IF_ROUND_ELSE(60, 20)));
}

static void flush_out(void);

static void retry_fired(void *ctx) {
  s_retry = NULL;
  flush_out();
}

static void retry_later(uint32_t ms) {
  if (!s_retry) s_retry = app_timer_register(ms, retry_fired, NULL);
}

// Sends the most important waiting message. Every message is idempotent, so a repeat is harmless.
static void flush_out(void) {
  if (s_out != OutNone) return;
  OutKind kind = s_q_pending ? OutQuestion : s_cancel_pending ? OutCancel : s_reset_pending ? OutReset
               : (s_busy && s_expect_audio && (s_freed_due || s_freed_total - s_freed_sent >= CREDIT_STEP))
                 ? OutFreed : OutNone;
  if (kind == OutNone) return;
  DictionaryIterator *it;
  if (app_message_outbox_begin(&it) != APP_MSG_OK) {
    retry_later(200);
    return;
  }
  switch (kind) {
    case OutQuestion:
      dict_write_cstring(it, MESSAGE_KEY_QUESTION, s_question);
      dict_write_int32(it, MESSAGE_KEY_SEQ, s_seq);
      // the phone may send this much audio before it hears back from the watch
      dict_write_int32(it, MESSAGE_KEY_CREDIT, s_expect_audio ? RING_SIZE : 0);
      dict_write_int32(it, MESSAGE_KEY_INBOX, s_inbox);
      dict_write_int32(it, MESSAGE_KEY_DICT_MS, s_dict_ms);
      break;
    case OutCancel:
      dict_write_int32(it, MESSAGE_KEY_CANCEL, 1);
      dict_write_int32(it, MESSAGE_KEY_SEQ, s_cancel_seq);
      break;
    case OutReset:
      dict_write_int32(it, MESSAGE_KEY_RESET, 1);
      break;
    default:
      s_freed_out = s_freed_total;
      s_freed_due = false;
      dict_write_int32(it, MESSAGE_KEY_FREED, s_freed_out);
      dict_write_int32(it, MESSAGE_KEY_SEQ, s_seq);
      dict_write_int32(it, MESSAGE_KEY_STALLS, s_stalls);
      break;
  }
  if (app_message_outbox_send() == APP_MSG_OK) {
    s_out = kind;
  } else {
    retry_later(200);
  }
}

static void outbox_sent(DictionaryIterator *it, void *context) {
  switch (s_out) {
    case OutQuestion: s_q_pending = false; break;
    case OutCancel: s_cancel_pending = false; break;
    case OutReset: s_reset_pending = false; break;
    case OutFreed: if (s_freed_out > s_freed_sent) s_freed_sent = s_freed_out; break;
    default: break;
  }
  s_out = OutNone;
  s_tries = 0;
  flush_out();
}

static void give_up(const char *status);

static void outbox_failed(DictionaryIterator *it, AppMessageResult reason, void *context) {
  OutKind kind = s_out;
  s_out = OutNone;
  APP_LOG(APP_LOG_LEVEL_WARNING, "send %d failed: %d", (int)kind, (int)reason);
  if (++s_tries >= SEND_TRIES) {
    s_tries = 0;
    if (kind == OutQuestion) {
      s_q_pending = false;
      give_up("Handy nicht erreichbar");
      return;
    }
    if (kind == OutCancel) s_cancel_pending = false;
    if (kind == OutReset) s_reset_pending = false;
  }
  retry_later(150 * s_tries + 100);
}

static void cancel_answer(void) {
  if (!s_busy) return;
  s_busy = false;
  if (s_q_pending) {       // never reached the phone: nothing to cancel there
    s_q_pending = false;
  } else {
    s_cancel_pending = true;
    s_cancel_seq = s_seq;
  }
  flush_out();
}

// ---------------------------------------------------------------- audio

static void audio_reset(void) {
  if (s_timer) {
    app_timer_cancel(s_timer);
    s_timer = NULL;
  }
  if (s_playing) {
    speaker_stop();
    speaker_stream_close();
  }
  s_playing = false;
  s_head = s_tail = s_fill = 0;
  s_rebuf = false;
  s_stalls = 0;
  s_audio_end = false;
  s_freed_total = s_freed_sent = s_freed_out = 0;
  s_pred = s_index = 0;
  s_pcm_len = s_pcm_off = 0;
  memset(s_levels, 0, sizeof(s_levels));
  s_tick_level = 0;
  face_set_level(0);
}

// The mouth follows what is heard, not what is decoded: the speaker queue holds about
// half a second, so the level of each tick is shown MOUTH_DELAY ticks later.
static void mouth_tick(void) {
  face_set_level(s_levels[s_level_pos]);
  s_levels[s_level_pos] = s_tick_level;
  s_level_pos = (s_level_pos + 1) % MOUTH_DELAY;
  s_tick_level = 0;
}

static void decode_block(void) {
  uint32_t n = s_fill < DECODE_BYTES ? s_fill : DECODE_BYTES;
  int pred = s_pred, index = s_index;
  for (uint32_t i = 0; i < n; i++) {
    uint8_t byte = s_ring[s_tail];
    s_tail = (s_tail + 1) % RING_SIZE;
    for (int h = 0; h < 2; h++) {
      int code = h ? byte >> 4 : byte & 15;
      int step = STEPS[index];
      int delta = step >> 3;
      if (code & 4) delta += step;
      if (code & 2) delta += step >> 1;
      if (code & 1) delta += step >> 2;
      pred += (code & 8) ? -delta : delta;
      if (pred > 32767) pred = 32767;
      if (pred < -32768) pred = -32768;
      index += INDEX[code & 7];
      if (index < 0) index = 0;
      if (index > 88) index = 88;
      s_pcm[i * 2 + h] = pred;
    }
  }
  int peak = 0;
  for (uint32_t i = 0; i < n * 2; i++) {
    int v = s_pcm[i] < 0 ? -s_pcm[i] : s_pcm[i];
    if (v > peak) peak = v;
  }
  peak >>= 6;
  if (peak > 255) peak = 255;
  if (peak > s_tick_level) s_tick_level = peak;
  s_pred = pred;
  s_index = index;
  s_fill -= n;
  s_freed_total += n;
  s_pcm_len = n * 4;
  s_pcm_off = 0;
}

static void drained(void *ctx) {
  if (!s_playing && !s_busy && !s_fill) face_set_mode(FaceIdle);
}

static void audio_tick(void *ctx) {
  s_timer = NULL;
  if (!s_playing) {
    if (s_fill >= PREBUFFER || (s_audio_end && s_fill > 0)) {
      s_playing = speaker_stream_open(SpeakerPcmFormat_8kHz_16bit, s_volume);
      if (!s_playing) {
        set_status("Lautsprecher belegt");
        return;
      }
      face_set_mode(FaceSpeak);
    } else if (s_audio_end) {
      return;
    }
  }
  if (s_playing && s_rebuf) {
    uint32_t need = REBUFFER + 2000 * (s_stalls - 1);
    if (need > REBUFFER_MAX) need = REBUFFER_MAX;
    if (s_fill >= need || s_audio_end) s_rebuf = false;
  }
  if (s_playing && !s_rebuf) {
    for (;;) {
      if (s_pcm_off >= s_pcm_len) {
        if (!s_fill) {
          // nothing left while more is coming: the speaker plays out its queue, then stays quiet
          // until the buffer holds enough again, so a slow connection gives one pause, not stutter
          if (!s_audio_end) {
            s_rebuf = true;
            s_stalls++;
          }
          break;
        }
        decode_block();
      }
      uint32_t want = s_pcm_len - s_pcm_off;
      uint32_t done = speaker_stream_write((uint8_t *)s_pcm + s_pcm_off, want);
      s_pcm_off += done;
      if (done < want) break;    // the speaker queue is full: continue on the next tick
    }
    mouth_tick();
    if (s_freed_total - s_freed_sent >= CREDIT_STEP) flush_out();
    if (s_audio_end && !s_fill && s_pcm_off >= s_pcm_len) {
      speaker_stream_close();    // the queued rest drains and plays out
      s_playing = false;
      if (!s_busy) set_status("SELECT: neue Frage");
      app_timer_register(MOUTH_DELAY * 40, drained, NULL);
      return;
    }
  }
  s_timer = app_timer_register(40, audio_tick, NULL);
}

static void audio_kick(void) {
  if (!s_timer) s_timer = app_timer_register(10, audio_tick, NULL);
}

static void audio_add(const uint8_t *data, uint16_t len) {
  for (uint16_t i = 0; i < len && s_fill < RING_SIZE; i++) {
    s_ring[s_head] = data[i];
    s_head = (s_head + 1) % RING_SIZE;
    s_fill++;
  }
  audio_kick();
}

// ---------------------------------------------------------------- asking

static void watchdog_tick(void *ctx);

static void watchdog_start(void) {
  if (!s_watchdog) s_watchdog = app_timer_register(1000, watchdog_tick, NULL);
}

static void give_up(const char *status) {
  cancel_answer();
  audio_reset();
  set_status(status);
  face_set_mode(FaceSad);
  vibes_double_pulse();
}

// Once a second while an answer runs: a lost buffer report would stop the speech for good, so it
// is repeated; and when the phone stays silent, the watch says so instead of waiting forever.
static void watchdog_tick(void *ctx) {
  s_watchdog = NULL;
  if (!s_busy) return;
  if (time(NULL) - s_last_rx > ANSWER_TIMEOUT) {
    give_up("Keine Antwort. SELECT: nochmal");
    return;
  }
  if (s_expect_audio && !s_audio_end && time(NULL) % FREED_EVERY == 0) {
    s_freed_due = true;
    flush_out();
  }
  watchdog_start();
}

static void ask(const char *text) {
  audio_reset();
  snprintf(s_question, sizeof(s_question), "%s", text);
  s_answer[0] = 0;
  update_text();
  scroll_layer_set_content_offset(s_scroll_layer, GPointZero, false);
  s_seq++;
  s_expect_audio = s_speak && s_ring;
  s_text_done = false;
  s_busy = true;
  s_last_rx = time(NULL);
  s_q_pending = true;
  s_tries = 0;
  flush_out();
  watchdog_start();
  set_status("Denke nach …");
  face_set_mode(FaceThink);
}

// The answer is complete when the text is in and, if speech was coming, its end too.
static void finish_if_done(void) {
  if (!s_busy || !s_text_done || (s_expect_audio && !s_audio_end)) return;
  s_busy = false;
  if (!s_playing && !s_fill) {
    set_status("SELECT: neue Frage");
    face_set_mode(FaceIdle);
    if (!s_expect_audio) vibes_short_pulse();
  } else {
    set_status("Spreche … SELECT: Stopp");
  }
}

static void dictation_done(DictationSession *session, DictationSessionStatus status,
                           char *transcription, void *ctx) {
  s_dict_ms = (int32_t)(time(NULL) - s_dict_start) * 1000;
  if (status == DictationSessionStatusSuccess && transcription && transcription[0]) {
    ask(transcription);
    return;
  }
  face_set_mode(FaceIdle);
  if (status == DictationSessionStatusFailureNoSpeechDetected) {
    set_status("Nichts gehört");
  } else if (status == DictationSessionStatusFailureConnectivityError) {
    set_status("Diktat: keine Verbindung");
    face_set_mode(FaceSad);
  } else if (status == DictationSessionStatusFailureDisabled) {
    set_status("Diktat ist aus");
  } else {
    set_status("SELECT: Frage stellen");
  }
}

static void listen(void) {
  cancel_answer();  // asking again cancels the running answer
  audio_reset();
  if (!s_dictation) {
    set_status("Kein Mikrofon");
    face_set_mode(FaceSad);
    return;
  }
  face_set_mode(FaceListen);
  s_dict_start = time(NULL);
  dictation_session_start(s_dictation);
}

static void select_click(ClickRecognizerRef recognizer, void *context) {
  if (s_playing || s_fill) {  // first press stops the speech
    audio_reset();
    cancel_answer();
    set_status("SELECT: neue Frage");
    face_set_mode(FaceIdle);
    return;
  }
  listen();
}

static void select_long(ClickRecognizerRef recognizer, void *context) {
  audio_reset();
  cancel_answer();
  s_reset_pending = true;
  flush_out();
  s_question[0] = 0;
  s_answer[0] = 0;
  update_text();
  vibes_short_pulse();
  set_status("Neues Gespräch");
  face_set_mode(FaceIdle);
}

static void click_config(void *context) {
  window_single_click_subscribe(BUTTON_ID_SELECT, select_click);
  window_long_click_subscribe(BUTTON_ID_SELECT, 600, select_long, NULL);
}

// ---------------------------------------------------------------- messages

static void inbox_received(DictionaryIterator *it, void *context) {
  Tuple *t;
  // answer parts carry the question's number: parts of a cancelled answer are dropped
  if ((t = dict_find(it, MESSAGE_KEY_SEQ))) {
    if (t->value->int32 != s_seq || !s_busy) return;
    s_last_rx = time(NULL);
  }
  if ((t = dict_find(it, MESSAGE_KEY_SPEAK))) {
    s_speak = t->value->int32 != 0;
    persist_write_bool(PERSIST_SPEAK, s_speak);
  }
  if ((t = dict_find(it, MESSAGE_KEY_VOLUME))) {
    s_volume = t->value->int32;
    persist_write_int(PERSIST_VOLUME, s_volume);
    if (s_playing) speaker_set_volume(s_volume);
  }
  if ((t = dict_find(it, MESSAGE_KEY_AUTOLISTEN))) {
    s_autolisten = t->value->int32 != 0;
    persist_write_bool(PERSIST_AUTOLISTEN, s_autolisten);
  }
  if ((t = dict_find(it, MESSAGE_KEY_FACE))) {
    // the face the admin picked in the panel (0 robot, 1 comic)
    persist_write_int(PERSIST_FACE, t->value->int32);
    face_set_kind(t->value->int32);
  }
  if ((t = dict_find(it, MESSAGE_KEY_STATUS))) {
    set_status(t->value->cstring);
  }
  if ((t = dict_find(it, MESSAGE_KEY_ANSWER))) {
    size_t have = strlen(s_answer);
    snprintf(s_answer + have, sizeof(s_answer) - have, "%s", t->value->cstring);
    update_text();
  }
  if ((t = dict_find(it, MESSAGE_KEY_AUDIO)) && s_ring && s_speak) {
    audio_add(t->value->data, t->length);
  }
  if ((t = dict_find(it, MESSAGE_KEY_AUDIO_END))) {
    s_audio_end = true;
    audio_kick();
    finish_if_done();
  }
  if ((t = dict_find(it, MESSAGE_KEY_ERROR))) {
    s_busy = false;
    s_q_pending = false;
    set_status("Fehler");
    face_set_mode(FaceSad);
    size_t have = strlen(s_answer);
    snprintf(s_answer + have, sizeof(s_answer) - have, "%s%s", have ? "\n\n" : "", t->value->cstring);
    update_text();
    vibes_double_pulse();
  }
  if ((t = dict_find(it, MESSAGE_KEY_DONE))) {
    s_text_done = true;
    if (t->value->int32 != 2) s_expect_audio = false;   // 2: speech follows
    finish_if_done();
  }
}

static void inbox_dropped(AppMessageResult reason, void *context) {
  APP_LOG(APP_LOG_LEVEL_WARNING, "dropped %d", (int)reason);
}

// ---------------------------------------------------------------- window

static void window_load(Window *window) {
  Layer *root = window_get_root_layer(window);
  GRect b = layer_get_bounds(root);
  // face on top, a status line under it, the conversation text below (scrolls with UP/DOWN)
  int face_h = b.size.h * 2 / 5;
  s_face_layer = face_create(GRect(0, PBL_IF_ROUND_ELSE(8, 2), b.size.w, face_h));
  layer_add_child(root, s_face_layer);
  int top = face_h + PBL_IF_ROUND_ELSE(10, 4);
  int status_h = 22;
  s_status_layer = text_layer_create(GRect(0, top, b.size.w, status_h));
  text_layer_set_font(s_status_layer, fonts_get_system_font(FONT_KEY_GOTHIC_18_BOLD));
  text_layer_set_text_alignment(s_status_layer, GTextAlignmentCenter);
  text_layer_set_background_color(s_status_layer, GColorClear);
  text_layer_set_text_color(s_status_layer, PBL_IF_COLOR_ELSE(GColorCobaltBlue, GColorBlack));
  layer_add_child(root, text_layer_get_layer(s_status_layer));

  GRect sb = GRect(0, top + status_h, b.size.w, b.size.h - top - status_h);
  s_scroll_layer = scroll_layer_create(sb);
  scroll_layer_set_click_config_onto_window(s_scroll_layer, window);
  scroll_layer_set_callbacks(s_scroll_layer, (ScrollLayerCallbacks){.click_config_provider = click_config});
  scroll_layer_set_shadow_hidden(s_scroll_layer, true);
  s_text_layer = text_layer_create(GRect(PBL_IF_ROUND_ELSE(20, 4), 4, sb.size.w - PBL_IF_ROUND_ELSE(40, 8), 2000));
  text_layer_set_font(s_text_layer, fonts_get_system_font(FONT_KEY_GOTHIC_24));
  text_layer_set_text_alignment(s_text_layer, PBL_IF_ROUND_ELSE(GTextAlignmentCenter, GTextAlignmentLeft));
  scroll_layer_add_child(s_scroll_layer, text_layer_get_layer(s_text_layer));
  layer_add_child(root, scroll_layer_get_layer(s_scroll_layer));
  set_status("SELECT: Frage stellen");
  update_text();
}

static void window_unload(Window *window) {
  text_layer_destroy(s_text_layer);
  scroll_layer_destroy(s_scroll_layer);
  text_layer_destroy(s_status_layer);
  face_destroy();
}

static void start_listening(void *ctx) {
  listen();
}

static void init(void) {
  if (persist_exists(PERSIST_SPEAK)) s_speak = persist_read_bool(PERSIST_SPEAK);
  if (persist_exists(PERSIST_VOLUME)) s_volume = persist_read_int(PERSIST_VOLUME);
  if (persist_exists(PERSIST_AUTOLISTEN)) s_autolisten = persist_read_bool(PERSIST_AUTOLISTEN);
  if (persist_exists(PERSIST_FACE)) face_set_kind(persist_read_int(PERSIST_FACE));
#if defined(PBL_SPEAKER)
  s_ring = malloc(RING_SIZE);
#endif
  s_dictation = dictation_session_create(sizeof(s_question), dictation_done, NULL);
  if (s_dictation) dictation_session_enable_confirmation(s_dictation, false);

  s_window = window_create();
  window_set_window_handlers(s_window, (WindowHandlers){.load = window_load, .unload = window_unload});
  window_stack_push(s_window, true);

  app_message_register_inbox_received(inbox_received);
  app_message_register_inbox_dropped(inbox_dropped);
  app_message_register_outbox_sent(outbox_sent);
  app_message_register_outbox_failed(outbox_failed);
  s_inbox = app_message_inbox_size_maximum();
  if (s_inbox > INBOX_MAX) s_inbox = INBOX_MAX;
  app_message_open(s_inbox, 1024);
  s_seq = (int32_t)(time(NULL) & 0xffff) * 16;
  if (s_autolisten) app_timer_register(500, start_listening, NULL);
}

static void deinit(void) {
  audio_reset();
  if (s_busy && !s_q_pending) {   // last word to the phone, no time to wait for retries
    DictionaryIterator *it;
    if (app_message_outbox_begin(&it) == APP_MSG_OK) {
      dict_write_int32(it, MESSAGE_KEY_CANCEL, 1);
      dict_write_int32(it, MESSAGE_KEY_SEQ, s_seq);
      app_message_outbox_send();
    }
  }
  if (s_dictation) dictation_session_destroy(s_dictation);
  window_destroy(s_window);
  free(s_ring);
}

int main(void) {
  init();
  app_event_loop();
  deinit();
}
