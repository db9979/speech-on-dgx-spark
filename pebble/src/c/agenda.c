// Reminders, timers and quick commands on the watch (watch app 2.0).
//
// The phone sends the profile's next reminders as lines "id|due|made|rep|text" (due and made in epoch seconds)
// and the quick commands one per line. Both are kept in persistent storage, every reminder gets a wake-up, so it
// rings at its time even when the phone is away. What the person presses on the alert (Später, Serie beenden)
// and the ring itself (so no other device of the profile rings it again) go back to the Spark through a small
// queue that survives the app closing.
#include "agenda.h"

#define AG_MAX 8               // wake-ups an app may hold
#define AG_TEXT 64
#define Q_MAX 12
#define Q_TEXT 64
#define OUT_MAX 3
#define SNOOZE_S 600
#define SNOOZE_COOKIE 100
#define RING_AGAIN_MS 30000
#define RINGS 3
#define CLOSE_AFTER_MS 2500    // a reminder that started the app closes it again (time to send its action)

#define P_AG_N 100
#define P_AG 101               // ... 108
#define P_Q_N 120
#define P_Q 121                // ... 132
#define P_OUT 140
#define P_SNOOZE 141

typedef struct {
  char id[12];
  int32_t due;
  int32_t made;
  uint8_t rep;
  char text[AG_TEXT];
} Entry;

typedef struct {
  char id[12];
  uint8_t act;
  char text[AG_TEXT];
} OutItem;

typedef struct {
  uint8_t n;
  OutItem items[OUT_MAX];
} OutQueue;

static Entry s_ag[AG_MAX];
static int s_ag_n;
static char s_q[Q_MAX][Q_TEXT];
static int s_q_n;
static Entry s_snooze;         // a reminder put off on the watch itself (rings even if the Spark never hears of it)
static OutQueue s_out;
static AgendaAskFn s_ask;
static void (*s_out_ready)(void);
static bool s_launched_by_wakeup;

// ---------------------------------------------------------------- storage

static void copy(char *dst, size_t n, const char *src, size_t len) {
  if (len >= n) len = n - 1;
  memcpy(dst, src, len);
  dst[len] = 0;
}

static void save_agenda(void) {
  persist_write_int(P_AG_N, s_ag_n);
  for (int i = 0; i < s_ag_n; i++) persist_write_data(P_AG + i, &s_ag[i], sizeof(Entry));
}

static void save_quick(void) {
  persist_write_int(P_Q_N, s_q_n);
  for (int i = 0; i < s_q_n; i++) persist_write_string(P_Q + i, s_q[i]);
}

static void save_out(void) {
  persist_write_data(P_OUT, &s_out, sizeof(s_out));
}

static void load(void) {
  s_ag_n = persist_exists(P_AG_N) ? persist_read_int(P_AG_N) : 0;
  if (s_ag_n < 0 || s_ag_n > AG_MAX) s_ag_n = 0;
  for (int i = 0; i < s_ag_n; i++) {
    if (persist_read_data(P_AG + i, &s_ag[i], sizeof(Entry)) != (int)sizeof(Entry)) {
      s_ag_n = i;
      break;
    }
    s_ag[i].text[AG_TEXT - 1] = 0;
    s_ag[i].id[sizeof(s_ag[i].id) - 1] = 0;
  }
  s_q_n = persist_exists(P_Q_N) ? persist_read_int(P_Q_N) : 0;
  if (s_q_n < 0 || s_q_n > Q_MAX) s_q_n = 0;
  for (int i = 0; i < s_q_n; i++) persist_read_string(P_Q + i, s_q[i], Q_TEXT);
  memset(&s_out, 0, sizeof(s_out));
  if (persist_exists(P_OUT)) persist_read_data(P_OUT, &s_out, sizeof(s_out));
  if (s_out.n > OUT_MAX) s_out.n = 0;
  memset(&s_snooze, 0, sizeof(s_snooze));
  if (persist_exists(P_SNOOZE)) persist_read_data(P_SNOOZE, &s_snooze, sizeof(s_snooze));
  s_snooze.text[AG_TEXT - 1] = 0;
}

// ---------------------------------------------------------------- wake-ups

static void schedule_all(void) {
  wakeup_cancel_all();
  time_t now = time(NULL);
  for (int i = 0; i < s_ag_n; i++) {
    if (s_ag[i].due <= now + 2) continue;
    // two wake-ups (of any app) less than a minute apart are refused: then a minute later
    for (int k = 0; k < 4; k++) {
      WakeupId w = wakeup_schedule(s_ag[i].due + k * 60, i, true);
      if (w >= 0 || w != E_RANGE) break;
    }
  }
  if (s_snooze.due > now + 2) {
    for (int k = 0; k < 4; k++) {
      WakeupId w = wakeup_schedule(s_snooze.due + k * 60, SNOOZE_COOKIE, true);
      if (w >= 0 || w != E_RANGE) break;
    }
  }
}

// ---------------------------------------------------------------- the queue to the Spark

static void out_add(const char *id, int act, const char *text) {
  if (s_out.n == OUT_MAX) {   // full: the oldest goes (its ring is long past)
    memmove(&s_out.items[0], &s_out.items[1], sizeof(OutItem) * (OUT_MAX - 1));
    s_out.n--;
  }
  OutItem *o = &s_out.items[s_out.n++];
  memset(o, 0, sizeof(*o));
  copy(o->id, sizeof(o->id), id, strlen(id));
  o->act = act;
  copy(o->text, sizeof(o->text), text, strlen(text));
  save_out();
  if (s_out_ready) s_out_ready();
}

bool agenda_out_peek(char *id, size_t id_len, int32_t *act, char *text, size_t text_len) {
  if (!s_out.n) return false;
  copy(id, id_len, s_out.items[0].id, strlen(s_out.items[0].id));
  *act = s_out.items[0].act;
  copy(text, text_len, s_out.items[0].text, strlen(s_out.items[0].text));
  return true;
}

void agenda_out_sent(void) {
  if (!s_out.n) return;
  memmove(&s_out.items[0], &s_out.items[1], sizeof(OutItem) * (OUT_MAX - 1));
  s_out.n--;
  save_out();
}

// ---------------------------------------------------------------- texts

static void when_text(char *buf, size_t n, int32_t due) {
  time_t now = time(NULL);
  int32_t left = due - (int32_t)now;
  if (left >= 0 && left < 3600) {
    snprintf(buf, n, "in %d:%02d", (int)(left / 60), (int)(left % 60));
    return;
  }
  time_t t = due;
  struct tm when = *localtime(&t);
  struct tm today = *localtime(&now);
  char hm[8];
  strftime(hm, sizeof(hm), clock_is_24h_style() ? "%H:%M" : "%I:%M", &when);
  if (when.tm_yday == today.tm_yday && when.tm_year == today.tm_year) {
    snprintf(buf, n, "Heute %s", hm);
  } else if ((when.tm_yday == today.tm_yday + 1 && when.tm_year == today.tm_year) ||
             (when.tm_yday == 0 && today.tm_mon == 11 && today.tm_mday == 31)) {
    snprintf(buf, n, "Morgen %s", hm);
  } else {
    static const char *DAYS[7] = {"So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"};
    snprintf(buf, n, "%s %d.%d. %s", DAYS[when.tm_wday], when.tm_mday, when.tm_mon + 1, hm);
  }
}

static void draw_symbol(GContext *ctx, int kind, GPoint c) {
  // drawn, not bitmaps: ✓, zZ, ✕, +, ■
  graphics_context_set_stroke_color(ctx, GColorWhite);
  graphics_context_set_fill_color(ctx, GColorWhite);
  graphics_context_set_stroke_width(ctx, 3);
  switch (kind) {
    case 0:
      graphics_draw_line(ctx, GPoint(c.x - 7, c.y), GPoint(c.x - 2, c.y + 5));
      graphics_draw_line(ctx, GPoint(c.x - 2, c.y + 5), GPoint(c.x + 7, c.y - 5));
      break;
    case 1:
      graphics_context_set_text_color(ctx, GColorWhite);
      graphics_draw_text(ctx, "zZ", fonts_get_system_font(FONT_KEY_GOTHIC_18_BOLD), GRect(c.x - 12, c.y - 13, 24, 22),
                         GTextOverflowModeFill, GTextAlignmentCenter, NULL);
      break;
    case 2:
      graphics_draw_line(ctx, GPoint(c.x - 6, c.y - 6), GPoint(c.x + 6, c.y + 6));
      graphics_draw_line(ctx, GPoint(c.x + 6, c.y - 6), GPoint(c.x - 6, c.y + 6));
      break;
    case 3:
      graphics_draw_line(ctx, GPoint(c.x - 7, c.y), GPoint(c.x + 7, c.y));
      graphics_draw_line(ctx, GPoint(c.x, c.y - 7), GPoint(c.x, c.y + 7));
      break;
    default:
      graphics_fill_rect(ctx, GRect(c.x - 6, c.y - 6, 12, 12), 0, GCornerNone);
      break;
  }
}

// the black bar on the right with up to three symbols (-1: none)
void agenda_draw_bar(GContext *ctx, GRect b, int up, int mid, int down) {
  int w = 30;
  int x = b.size.w - w - PBL_IF_ROUND_ELSE(14, 0);
  graphics_context_set_fill_color(ctx, GColorBlack);
  graphics_fill_rect(ctx, GRect(x, 0, w, b.size.h), 0, GCornerNone);
  int cx = x + w / 2;
  if (up >= 0) draw_symbol(ctx, up, GPoint(cx, b.size.h / 6));
  if (mid >= 0) draw_symbol(ctx, mid, GPoint(cx, b.size.h / 2));
  if (down >= 0) draw_symbol(ctx, down, GPoint(cx, b.size.h * 5 / 6));
}

// ---------------------------------------------------------------- the alert

static Window *s_alert;
static Layer *s_alert_layer;
static Entry s_alert_e;
static int s_rings;
static AppTimer *s_ring_timer;
static AppTimer *s_close_timer;

static void ring(void) {
  static const uint32_t SEGS[] = {400, 200, 400, 200, 800};
  VibePattern pat = {.durations = SEGS, .num_segments = ARRAY_LENGTH(SEGS)};
  vibes_enqueue_custom_pattern(pat);
  light_enable_interaction();
}

static void ring_again(void *ctx) {
  s_ring_timer = NULL;
  if (!s_alert || ++s_rings >= RINGS) return;
  ring();
  s_ring_timer = app_timer_register(RING_AGAIN_MS, ring_again, NULL);
}

static void close_app(void *ctx) {
  s_close_timer = NULL;
  window_stack_pop_all(true);
}

static void alert_done(void) {
  if (s_ring_timer) {
    app_timer_cancel(s_ring_timer);
    s_ring_timer = NULL;
  }
  vibes_cancel();
  if (s_alert) window_stack_remove(s_alert, true);
  // started by the reminder: close again once its action had time to reach the phone (else it waits in the queue)
  if (s_launched_by_wakeup && !s_close_timer) s_close_timer = app_timer_register(CLOSE_AFTER_MS, close_app, NULL);
}

static void alert_draw(Layer *layer, GContext *ctx) {
  GRect b = layer_get_bounds(layer);
  graphics_context_set_fill_color(ctx, PBL_IF_COLOR_ELSE(GColorChromeYellow, GColorWhite));
  graphics_fill_rect(ctx, b, 0, GCornerNone);
  int tw = b.size.w - 30 - PBL_IF_ROUND_ELSE(40, 12);
  int left = PBL_IF_ROUND_ELSE(24, 8);
  // a bell
  int bx = left + tw / 2, by = PBL_IF_ROUND_ELSE(34, 28);
  graphics_context_set_fill_color(ctx, GColorBlack);
  graphics_fill_circle(ctx, GPoint(bx, by), 14);
  graphics_fill_rect(ctx, GRect(bx - 14, by, 29, 14), 0, GCornerNone);
  graphics_fill_rect(ctx, GRect(bx - 19, by + 13, 39, 4), 2, GCornersAll);
  graphics_fill_circle(ctx, GPoint(bx, by + 21), 4);
  char head[32], hm[8];
  time_t t = s_alert_e.due;
  strftime(hm, sizeof(hm), clock_is_24h_style() ? "%H:%M" : "%I:%M", localtime(&t));
  snprintf(head, sizeof(head), "ERINNERUNG · %s", hm);
  graphics_context_set_text_color(ctx, GColorBlack);
  graphics_draw_text(ctx, head, fonts_get_system_font(FONT_KEY_GOTHIC_14_BOLD), GRect(left, by + 32, tw, 18),
                     GTextOverflowModeTrailingEllipsis, PBL_IF_ROUND_ELSE(GTextAlignmentCenter, GTextAlignmentLeft), NULL);
  graphics_draw_text(ctx, s_alert_e.text, fonts_get_system_font(FONT_KEY_GOTHIC_24_BOLD),
                     GRect(left, by + 48, tw, b.size.h - by - 52), GTextOverflowModeTrailingEllipsis,
                     PBL_IF_ROUND_ELSE(GTextAlignmentCenter, GTextAlignmentLeft), NULL);
  agenda_draw_bar(ctx, b, 0, 1, 2);
}

static void alert_ok(ClickRecognizerRef r, void *ctx) {
  alert_done();
}

static void alert_snooze(ClickRecognizerRef r, void *ctx) {
  out_add(s_alert_e.id, ActSnooze, s_alert_e.text);
  // rings in 10 minutes from the watch itself; the Spark's new reminder replaces it at the next sync
  s_snooze = s_alert_e;
  s_snooze.due = (int32_t)time(NULL) + SNOOZE_S;
  persist_write_data(P_SNOOZE, &s_snooze, sizeof(s_snooze));
  schedule_all();
  alert_done();
}

static void alert_stop(ClickRecognizerRef r, void *ctx) {
  if (s_alert_e.rep) out_add(s_alert_e.id, ActStop, s_alert_e.text);   // the series ends; a single one is just closed
  alert_done();
}

static void alert_clicks(void *ctx) {
  window_single_click_subscribe(BUTTON_ID_UP, alert_ok);
  window_single_click_subscribe(BUTTON_ID_SELECT, alert_snooze);
  window_single_click_subscribe(BUTTON_ID_DOWN, alert_stop);
}

static void alert_load(Window *w) {
  Layer *root = window_get_root_layer(w);
  s_alert_layer = layer_create(layer_get_bounds(root));
  layer_set_update_proc(s_alert_layer, alert_draw);
  layer_add_child(root, s_alert_layer);
}

static void alert_unload(Window *w) {
  layer_destroy(s_alert_layer);
  s_alert_layer = NULL;
  window_destroy(w);
  if (s_alert == w) s_alert = NULL;
  if (s_ring_timer) {
    app_timer_cancel(s_ring_timer);
    s_ring_timer = NULL;
  }
}

static void alert_show(const Entry *e) {
  s_alert_e = *e;
  if (!s_alert) {
    s_alert = window_create();
    window_set_click_config_provider(s_alert, alert_clicks);
    window_set_window_handlers(s_alert, (WindowHandlers){.load = alert_load, .unload = alert_unload});
    window_stack_push(s_alert, true);
  } else if (s_alert_layer) {
    layer_mark_dirty(s_alert_layer);
  }
  s_rings = 0;
  ring();
  if (s_ring_timer) app_timer_cancel(s_ring_timer);
  s_ring_timer = app_timer_register(RING_AGAIN_MS, ring_again, NULL);
  out_add(e->id, ActPlayed, "");   // rung here: no other device of the profile rings it again
}

static void woke(WakeupId id, int32_t cookie) {
  if (cookie == SNOOZE_COOKIE) {
    Entry e = s_snooze;
    memset(&s_snooze, 0, sizeof(s_snooze));
    persist_delete(P_SNOOZE);
    if (e.text[0]) alert_show(&e);
    return;
  }
  // the wake-up's number is the place in the list; the list may have changed since: take the one due now
  time_t now = time(NULL);
  int best = -1;
  for (int i = 0; i < s_ag_n; i++) {
    if (s_ag[i].due <= now + 30 && s_ag[i].due > now - 600 && (best < 0 || s_ag[i].due > s_ag[best].due)) best = i;
  }
  if (best < 0 && cookie >= 0 && cookie < s_ag_n) best = cookie;
  if (best >= 0) alert_show(&s_ag[best]);
}

// ---------------------------------------------------------------- a timer up close

static Window *s_timer_win;
static Layer *s_timer_layer;
static int s_timer_i;
static AppTimer *s_tick;

static void timer_draw(Layer *layer, GContext *ctx) {
  GRect b = layer_get_bounds(layer);
  graphics_context_set_fill_color(ctx, GColorBlack);
  graphics_fill_rect(ctx, b, 0, GCornerNone);
  if (s_timer_i < 0 || s_timer_i >= s_ag_n) return;
  Entry *e = &s_ag[s_timer_i];
  int32_t now = (int32_t)time(NULL);
  int32_t left = e->due - now;
  if (left < 0) left = 0;
  int area = b.size.w - 30 - PBL_IF_ROUND_ELSE(14, 0);
  int r = (area < b.size.h ? area : b.size.h) / 2 - 14;
  GPoint c = GPoint(area / 2 + PBL_IF_ROUND_ELSE(8, 0), b.size.h / 2 - 8);
  GRect ringr = GRect(c.x - r, c.y - r, 2 * r, 2 * r);
  graphics_context_set_fill_color(ctx, GColorDarkGray);
  graphics_fill_radial(ctx, ringr, GOvalScaleModeFitCircle, 10, 0, TRIG_MAX_ANGLE);
  int32_t total = e->made > 0 ? e->due - e->made : 0;
  if (total > 0 && total <= 6 * 3600) {
    int32_t angle = (int32_t)((int64_t)TRIG_MAX_ANGLE * left / total);
    graphics_context_set_fill_color(ctx, PBL_IF_COLOR_ELSE(GColorGreen, GColorWhite));
    graphics_fill_radial(ctx, ringr, GOvalScaleModeFitCircle, 10, 0, angle);
  }
  char big[16];
  if (left >= 3600) {
    snprintf(big, sizeof(big), "%d:%02d:%02d", (int)(left / 3600), (int)(left / 60 % 60), (int)(left % 60));
  } else {
    snprintf(big, sizeof(big), "%02d:%02d", (int)(left / 60), (int)(left % 60));
  }
  graphics_context_set_text_color(ctx, GColorWhite);
  graphics_draw_text(ctx, big, fonts_get_system_font(left >= 3600 ? FONT_KEY_GOTHIC_24_BOLD : FONT_KEY_BITHAM_30_BLACK),
                     GRect(c.x - r, c.y - 22, 2 * r, 34), GTextOverflowModeFill, GTextAlignmentCenter, NULL);
  graphics_context_set_text_color(ctx, PBL_IF_COLOR_ELSE(GColorGreen, GColorWhite));
  graphics_draw_text(ctx, e->text, fonts_get_system_font(FONT_KEY_GOTHIC_14), GRect(c.x - r + 10, c.y + 12, 2 * r - 20, 32),
                     GTextOverflowModeTrailingEllipsis, GTextAlignmentCenter, NULL);
  agenda_draw_bar(ctx, b, 3, -1, 4);
}

static void timer_tick(void *ctx) {
  s_tick = NULL;
  if (!s_timer_layer) return;
  layer_mark_dirty(s_timer_layer);
  s_tick = app_timer_register(1000, timer_tick, NULL);
}

static void timer_plus(ClickRecognizerRef r, void *ctx) {
  if (s_timer_i < 0 || s_timer_i >= s_ag_n) return;
  Entry *e = &s_ag[s_timer_i];
  int32_t now = (int32_t)time(NULL);
  e->due = (e->due > now ? e->due : now) + 60;
  out_add(e->id, ActPlus, e->text);
  save_agenda();
  schedule_all();
  layer_mark_dirty(s_timer_layer);
}

static void timer_cancel(ClickRecognizerRef r, void *ctx) {
  if (s_timer_i < 0 || s_timer_i >= s_ag_n) return;
  out_add(s_ag[s_timer_i].id, ActCancel, s_ag[s_timer_i].text);
  memmove(&s_ag[s_timer_i], &s_ag[s_timer_i + 1], sizeof(Entry) * (s_ag_n - s_timer_i - 1));
  s_ag_n--;
  save_agenda();
  schedule_all();
  vibes_short_pulse();
  window_stack_remove(s_timer_win, true);
}

static void timer_clicks(void *ctx) {
  window_single_click_subscribe(BUTTON_ID_UP, timer_plus);
  window_long_click_subscribe(BUTTON_ID_DOWN, 700, timer_cancel, NULL);   // held: a slip does not stop it
}

static void timer_load(Window *w) {
  Layer *root = window_get_root_layer(w);
  s_timer_layer = layer_create(layer_get_bounds(root));
  layer_set_update_proc(s_timer_layer, timer_draw);
  layer_add_child(root, s_timer_layer);
  s_tick = app_timer_register(1000, timer_tick, NULL);
}

static void timer_unload(Window *w) {
  if (s_tick) {
    app_timer_cancel(s_tick);
    s_tick = NULL;
  }
  layer_destroy(s_timer_layer);
  s_timer_layer = NULL;
  window_destroy(w);
  if (s_timer_win == w) s_timer_win = NULL;
}

static void timer_show(int i) {
  s_timer_i = i;
  if (s_timer_win) return;
  s_timer_win = window_create();
  window_set_click_config_provider(s_timer_win, timer_clicks);
  window_set_window_handlers(s_timer_win, (WindowHandlers){.load = timer_load, .unload = timer_unload});
  window_stack_push(s_timer_win, true);
}

// ---------------------------------------------------------------- the two lists

typedef enum { ListAgenda, ListQuick } ListKind;
static Window *s_list_win;
static MenuLayer *s_menu;
static ListKind s_list;
static AppTimer *s_list_tick;
static char s_sub[32];

static uint16_t rows(MenuLayer *m, uint16_t section, void *ctx) {
  int n = s_list == ListAgenda ? s_ag_n : s_q_n;
  return n ? n : 1;
}

static void draw_row(GContext *ctx, const Layer *cell, MenuIndex *idx, void *data) {
  if (s_list == ListAgenda) {
    if (!s_ag_n) {
      menu_cell_basic_draw(ctx, cell, "Nichts geplant", "Sag: Timer 10 Minuten", NULL);
      return;
    }
    Entry *e = &s_ag[idx->row];
    char when[24];
    when_text(when, sizeof(when), e->due);
    snprintf(s_sub, sizeof(s_sub), "%s%s", when, e->rep ? " · immer" : "");
    menu_cell_basic_draw(ctx, cell, e->text, s_sub, NULL);
  } else {
    if (!s_q_n) {
      menu_cell_basic_draw(ctx, cell, "Keine Befehle", "Ich > Pebble-Uhr", NULL);
      return;
    }
    menu_cell_basic_draw(ctx, cell, s_q[idx->row], NULL, NULL);
  }
}

static int16_t row_height(MenuLayer *m, MenuIndex *idx, void *ctx) {
  return s_list == ListQuick && s_q_n ? 36 : 48;
}

static void picked(MenuLayer *m, MenuIndex *idx, void *ctx) {
  if (s_list == ListAgenda) {
    if (idx->row < s_ag_n) timer_show(idx->row);
    return;
  }
  if (idx->row >= s_q_n) return;
  static char text[Q_TEXT];
  snprintf(text, sizeof(text), "%s", s_q[idx->row]);
  window_stack_remove(s_list_win, true);
  if (s_ask) s_ask(text);
}

static void list_tick(void *ctx) {
  s_list_tick = NULL;
  if (!s_menu) return;
  menu_layer_reload_data(s_menu);   // the time left counts down
  s_list_tick = app_timer_register(1000, list_tick, NULL);
}

static void list_load(Window *w) {
  Layer *root = window_get_root_layer(w);
  s_menu = menu_layer_create(layer_get_bounds(root));
  menu_layer_set_callbacks(s_menu, NULL, (MenuLayerCallbacks){
    .get_num_rows = rows, .draw_row = draw_row, .get_cell_height = row_height, .select_click = picked});
#if defined(PBL_COLOR)
  menu_layer_set_highlight_colors(s_menu, GColorVividCerulean, GColorWhite);
#endif
  menu_layer_set_click_config_onto_window(s_menu, w);
  layer_add_child(root, menu_layer_get_layer(s_menu));
  if (s_list == ListAgenda) s_list_tick = app_timer_register(1000, list_tick, NULL);
}

static void list_unload(Window *w) {
  if (s_list_tick) {
    app_timer_cancel(s_list_tick);
    s_list_tick = NULL;
  }
  menu_layer_destroy(s_menu);
  s_menu = NULL;
  window_destroy(w);
  if (s_list_win == w) s_list_win = NULL;
}

static void list_show(ListKind kind) {
  if (s_list_win) {   // the other list is open: switch it over
    s_list = kind;
    if (s_menu) menu_layer_reload_data(s_menu);
    return;
  }
  s_list = kind;
  s_list_win = window_create();
  window_set_window_handlers(s_list_win, (WindowHandlers){.load = list_load, .unload = list_unload});
  window_stack_push(s_list_win, true);
}

void agenda_show_list(void) {
  list_show(ListAgenda);
}

void quick_show_list(void) {
  list_show(ListQuick);
}

// ---------------------------------------------------------------- from the phone

void agenda_set(const char *lines) {
  int n = 0;
  const char *p = lines;
  while (*p && n < AG_MAX) {
    const char *end = strchr(p, '\n');
    size_t len = end ? (size_t)(end - p) : strlen(p);
    // id|due|made|rep|text
    const char *f[5];
    size_t fl[5];
    int k = 0;
    const char *q = p;
    while (k < 4) {
      const char *bar = NULL;
      for (const char *x = q; x < p + len; x++) {
        if (*x == '|') {
          bar = x;
          break;
        }
      }
      if (!bar) break;
      f[k] = q;
      fl[k] = bar - q;
      k++;
      q = bar + 1;
    }
    if (k == 4) {
      f[4] = q;
      fl[4] = len - (q - p);
      Entry *e = &s_ag[n];
      memset(e, 0, sizeof(*e));
      copy(e->id, sizeof(e->id), f[0], fl[0]);
      char num[16];
      copy(num, sizeof(num), f[1], fl[1]);
      e->due = atoi(num);
      copy(num, sizeof(num), f[2], fl[2]);
      e->made = atoi(num);
      e->rep = fl[3] && f[3][0] == '1';
      copy(e->text, sizeof(e->text), f[4], fl[4]);
      if (e->id[0] && e->due > 0) n++;
    }
    if (!end) break;
    p = end + 1;
  }
  s_ag_n = n;
  // the Spark knows about the put-off one now (its new reminder is in the list): the watch's own goes
  if (s_snooze.due) {
    for (int i = 0; i < s_ag_n; i++) {
      if (strcmp(s_ag[i].text, s_snooze.text) == 0 && s_ag[i].due >= s_snooze.due - 120) {
        memset(&s_snooze, 0, sizeof(s_snooze));
        persist_delete(P_SNOOZE);
        break;
      }
    }
  }
  save_agenda();
  schedule_all();
  if (s_menu) menu_layer_reload_data(s_menu);
  if (s_timer_win && s_timer_i >= s_ag_n) window_stack_remove(s_timer_win, true);
}

void agenda_off(void) {
  s_ag_n = 0;
  save_agenda();
  memset(&s_snooze, 0, sizeof(s_snooze));
  persist_delete(P_SNOOZE);
  wakeup_cancel_all();
  if (s_menu) menu_layer_reload_data(s_menu);
}

void quick_set(const char *lines) {
  int n = 0;
  const char *p = lines;
  while (*p && n < Q_MAX) {
    const char *end = strchr(p, '\n');
    size_t len = end ? (size_t)(end - p) : strlen(p);
    if (len) copy(s_q[n++], Q_TEXT, p, len);
    if (!end) break;
    p = end + 1;
  }
  s_q_n = n;
  save_quick();
  if (s_menu) menu_layer_reload_data(s_menu);
}

// ---------------------------------------------------------------- start and end

void agenda_init(AgendaAskFn ask, void (*out_ready)(void)) {
  s_ask = ask;
  s_out_ready = out_ready;
  load();
  wakeup_service_subscribe(woke);
}

bool agenda_launch(void) {
  if (launch_reason() != APP_LAUNCH_WAKEUP) return false;
  WakeupId id;
  int32_t cookie;
  if (!wakeup_get_launch_event(&id, &cookie)) return false;
  s_launched_by_wakeup = true;
  woke(id, cookie);
  return true;
}

void agenda_deinit(void) {
  if (s_close_timer) app_timer_cancel(s_close_timer);
}
