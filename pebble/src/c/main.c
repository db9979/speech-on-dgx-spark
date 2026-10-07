// Spark: voice assistant on the watch. SELECT asks (dictation via the phone), the phone
// fetches the answer from the DGX Spark and sends text plus 8 kHz IMA ADPCM audio,
// which plays on the watch speaker.
#include <pebble.h>

#define ANSWER_MAX 3000
#define RING_SIZE 16384        // ADPCM bytes: 4 s of speech
#define PREBUFFER 3000         // start playing after 0.75 s of audio (or at the end)
#define CREDIT_STEP 2048       // tell the phone about freed space in steps of this
#define DECODE_BYTES 128       // ADPCM bytes decoded per speaker write (256 samples)
#define PERSIST_SPEAK 1
#define PERSIST_VOLUME 2
#define PERSIST_AUTOLISTEN 3

static Window *s_window;
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

// audio
static uint8_t *s_ring;
static uint32_t s_head, s_tail, s_fill;
static bool s_audio_end, s_playing;
static uint32_t s_freed;
static int s_pred, s_index;
static int16_t s_pcm[DECODE_BYTES * 2];
static uint32_t s_pcm_len, s_pcm_off;   // bytes of s_pcm not yet accepted by the speaker
static AppTimer *s_timer;

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

static void send_int(uint32_t key, int value) {
  DictionaryIterator *it;
  if (app_message_outbox_begin(&it) == APP_MSG_OK) {
    dict_write_int32(it, key, value);
    app_message_outbox_send();
  }
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
  s_audio_end = false;
  s_freed = 0;
  s_pred = s_index = 0;
  s_pcm_len = s_pcm_off = 0;
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
  s_pred = pred;
  s_index = index;
  s_fill -= n;
  s_freed += n;
  s_pcm_len = n * 4;
  s_pcm_off = 0;
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
    } else if (s_audio_end) {
      return;
    }
  }
  if (s_playing) {
    for (;;) {
      if (s_pcm_off >= s_pcm_len) {
        if (!s_fill) break;
        decode_block();
      }
      uint32_t want = s_pcm_len - s_pcm_off;
      uint32_t done = speaker_stream_write((uint8_t *)s_pcm + s_pcm_off, want);
      s_pcm_off += done;
      if (done < want) break;    // the speaker queue is full: continue on the next tick
    }
    if (s_freed >= CREDIT_STEP) {
      send_int(MESSAGE_KEY_CREDIT, s_freed);
      s_freed = 0;
    }
    if (s_audio_end && !s_fill && s_pcm_off >= s_pcm_len) {
      speaker_stream_close();    // the queued rest drains and plays out
      s_playing = false;
      if (!s_busy) set_status("SELECT: neue Frage");
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

static void ask(const char *text) {
  audio_reset();
  snprintf(s_question, sizeof(s_question), "%s", text);
  s_answer[0] = 0;
  update_text();
  scroll_layer_set_content_offset(s_scroll_layer, GPointZero, false);
  DictionaryIterator *it;
  if (app_message_outbox_begin(&it) != APP_MSG_OK) {
    set_status("Handy nicht erreichbar");
    return;
  }
  dict_write_cstring(it, MESSAGE_KEY_QUESTION, text);
  // the phone may send this much audio before it waits for CREDIT
  dict_write_int32(it, MESSAGE_KEY_CREDIT, (s_speak && s_ring) ? RING_SIZE : 0);
  app_message_outbox_send();
  s_busy = true;
  set_status("Denke nach …");
}

static void dictation_done(DictationSession *session, DictationSessionStatus status,
                           char *transcription, void *ctx) {
  if (status == DictationSessionStatusSuccess && transcription && transcription[0]) {
    ask(transcription);
  } else if (status == DictationSessionStatusFailureNoSpeechDetected) {
    set_status("Nichts gehört");
  } else if (status == DictationSessionStatusFailureConnectivityError) {
    set_status("Diktat: keine Verbindung");
  } else if (status == DictationSessionStatusFailureDisabled) {
    set_status("Diktat ist aus");
  } else {
    set_status("SELECT: Frage stellen");
  }
}

static void listen(void) {
  if (s_busy) {  // asking again cancels the running answer
    send_int(MESSAGE_KEY_CANCEL, 1);
    s_busy = false;
  }
  audio_reset();
  if (!s_dictation) {
    set_status("Kein Mikrofon");
    return;
  }
  dictation_session_start(s_dictation);
}

static void select_click(ClickRecognizerRef recognizer, void *context) {
  if (s_playing || s_fill) {  // first press stops the speech
    audio_reset();
    if (s_busy) {
      send_int(MESSAGE_KEY_CANCEL, 1);
      s_busy = false;
    }
    set_status("SELECT: neue Frage");
    return;
  }
  listen();
}

static void select_long(ClickRecognizerRef recognizer, void *context) {
  audio_reset();
  if (s_busy) send_int(MESSAGE_KEY_CANCEL, 1);
  s_busy = false;
  send_int(MESSAGE_KEY_RESET, 1);
  s_question[0] = 0;
  s_answer[0] = 0;
  update_text();
  vibes_short_pulse();
  set_status("Neues Gespräch");
}

static void click_config(void *context) {
  window_single_click_subscribe(BUTTON_ID_SELECT, select_click);
  window_long_click_subscribe(BUTTON_ID_SELECT, 600, select_long, NULL);
}

// ---------------------------------------------------------------- messages

static void inbox_received(DictionaryIterator *it, void *context) {
  Tuple *t;
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
  }
  if ((t = dict_find(it, MESSAGE_KEY_ERROR))) {
    s_busy = false;
    set_status("Fehler");
    size_t have = strlen(s_answer);
    snprintf(s_answer + have, sizeof(s_answer) - have, "%s%s", have ? "\n\n" : "", t->value->cstring);
    update_text();
    vibes_double_pulse();
  }
  if ((t = dict_find(it, MESSAGE_KEY_DONE))) {
    s_busy = false;
    if (!s_playing && !s_fill) {
      set_status("SELECT: neue Frage");
      if (!s_speak || !s_ring) vibes_short_pulse();
    } else {
      set_status("Spreche … SELECT: Stopp");
    }
  }
}

static void inbox_dropped(AppMessageResult reason, void *context) {
  APP_LOG(APP_LOG_LEVEL_WARNING, "dropped %d", (int)reason);
}

// ---------------------------------------------------------------- window

static void window_load(Window *window) {
  Layer *root = window_get_root_layer(window);
  GRect b = layer_get_bounds(root);
  int top = PBL_IF_ROUND_ELSE(30, 0);
  int status_h = 26;
  s_status_layer = text_layer_create(GRect(0, top, b.size.w, status_h));
  text_layer_set_font(s_status_layer, fonts_get_system_font(FONT_KEY_GOTHIC_18_BOLD));
  text_layer_set_text_alignment(s_status_layer, GTextAlignmentCenter);
  text_layer_set_background_color(s_status_layer, PBL_IF_COLOR_ELSE(GColorCobaltBlue, GColorBlack));
  text_layer_set_text_color(s_status_layer, GColorWhite);
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
}

static void start_listening(void *ctx) {
  listen();
}

static void init(void) {
  if (persist_exists(PERSIST_SPEAK)) s_speak = persist_read_bool(PERSIST_SPEAK);
  if (persist_exists(PERSIST_VOLUME)) s_volume = persist_read_int(PERSIST_VOLUME);
  if (persist_exists(PERSIST_AUTOLISTEN)) s_autolisten = persist_read_bool(PERSIST_AUTOLISTEN);
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
  uint32_t inbox = app_message_inbox_size_maximum();
  app_message_open(inbox > 4096 ? 4096 : inbox, 1024);
  if (s_autolisten) app_timer_register(500, start_listening, NULL);
}

static void deinit(void) {
  audio_reset();
  if (s_busy) send_int(MESSAGE_KEY_CANCEL, 1);
  if (s_dictation) dictation_session_destroy(s_dictation);
  window_destroy(s_window);
  free(s_ring);
}

int main(void) {
  init();
  app_event_loop();
  deinit();
}
