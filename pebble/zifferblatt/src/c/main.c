// Spark-Zifferblatt: a watchface of its own (plan pebble-ideen/plan.md, idea 1 with 7). It shows the time and
// what the Spark knows for the profile: the next appointment, the next reminder, the weather, a hint and, for
// admins, a service that does not answer (a red bar, one double buzz when it is new). Every 15 minutes the watch
// asks the phone (REFRESH); the phone fetches GET /api/watch/blick and sends the parts. They are kept in storage,
// so the face shows them at once after a restart.
#include <pebble.h>

#define TEXT_LEN 64
#define REFRESH_MIN 15

enum { P_NEXT_T = 1, P_NEXT, P_REM_T, P_REM, P_WX, P_ALERT, P_TIP, P_WHERE };

static Window *s_window;
static Layer *s_layer;
static char s_next[TEXT_LEN], s_rem[TEXT_LEN], s_wx[TEXT_LEN], s_alert[TEXT_LEN], s_tip[TEXT_LEN];
static char s_status[TEXT_LEN];
static int32_t s_next_t, s_rem_t;
static bool s_where_out;
static bool s_refresh_pending;

// ---------------------------------------------------------------- storage

static void load(void) {
  if (persist_exists(P_NEXT_T)) s_next_t = persist_read_int(P_NEXT_T);
  if (persist_exists(P_REM_T)) s_rem_t = persist_read_int(P_REM_T);
  if (persist_exists(P_NEXT)) persist_read_string(P_NEXT, s_next, sizeof(s_next));
  if (persist_exists(P_REM)) persist_read_string(P_REM, s_rem, sizeof(s_rem));
  if (persist_exists(P_WX)) persist_read_string(P_WX, s_wx, sizeof(s_wx));
  if (persist_exists(P_ALERT)) persist_read_string(P_ALERT, s_alert, sizeof(s_alert));
  if (persist_exists(P_TIP)) persist_read_string(P_TIP, s_tip, sizeof(s_tip));
  if (persist_exists(P_WHERE)) s_where_out = persist_read_bool(P_WHERE);
}

static void keep(int key, char *dst, const char *src) {
  snprintf(dst, TEXT_LEN, "%s", src);
  persist_write_string(key, dst);
}

// ---------------------------------------------------------------- drawing

static const char *DAYS[] = {"So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"};

static void when_text(char *out, size_t n, int32_t t) {
  time_t now = time(NULL);
  int32_t left = t - (int32_t)now;
  if (left >= 0 && left < 3600) {
    snprintf(out, n, "in %d Min", (int)((left + 59) / 60));
    return;
  }
  time_t at = (time_t)t;
  struct tm then = *localtime(&at);
  struct tm today = *localtime(&now);
  if (then.tm_yday == today.tm_yday && then.tm_year == today.tm_year) {
    snprintf(out, n, "%02d:%02d", then.tm_hour, then.tm_min);
  } else {
    snprintf(out, n, "%s %02d:%02d", DAYS[then.tm_wday], then.tm_hour, then.tm_min);
  }
}

static void icon_calendar(GContext *ctx, GPoint at) {
  graphics_context_set_stroke_color(ctx, GColorWhite);
  graphics_draw_rect(ctx, GRect(at.x, at.y + 2, 12, 11));
  graphics_context_set_fill_color(ctx, PBL_IF_COLOR_ELSE(GColorVividCerulean, GColorWhite));
  graphics_fill_rect(ctx, GRect(at.x, at.y + 2, 12, 4), 0, GCornerNone);
}

static void icon_bell(GContext *ctx, GPoint at) {
  graphics_context_set_fill_color(ctx, PBL_IF_COLOR_ELSE(GColorYellow, GColorWhite));
  graphics_fill_circle(ctx, GPoint(at.x + 6, at.y + 7), 5);
  graphics_fill_rect(ctx, GRect(at.x + 1, at.y + 7, 11, 5), 0, GCornerNone);
  graphics_fill_circle(ctx, GPoint(at.x + 6, at.y + 13), 1);
}

static void icon_sun(GContext *ctx, GPoint at) {
  graphics_context_set_fill_color(ctx, PBL_IF_COLOR_ELSE(GColorChromeYellow, GColorWhite));
  graphics_fill_circle(ctx, GPoint(at.x + 6, at.y + 8), 4);
  graphics_context_set_stroke_color(ctx, PBL_IF_COLOR_ELSE(GColorChromeYellow, GColorWhite));
  graphics_draw_circle(ctx, GPoint(at.x + 6, at.y + 8), 6);
}

static int line(GContext *ctx, GRect b, int y, void (*icon)(GContext *, GPoint), const char *text, GFont font) {
  int x = b.origin.x + PBL_IF_ROUND_ELSE(34, 6);
  int w = b.size.w - 2 * PBL_IF_ROUND_ELSE(34, 6);
  if (icon) icon(ctx, GPoint(x, y + 3));
  graphics_context_set_text_color(ctx, GColorWhite);
  graphics_draw_text(ctx, text, font, GRect(x + (icon ? 18 : 0), y, w - (icon ? 18 : 0), 22),
                     GTextOverflowModeTrailingEllipsis, icon ? GTextAlignmentLeft : PBL_IF_ROUND_ELSE(GTextAlignmentCenter, GTextAlignmentLeft), NULL);
  return y + 22;
}

static void draw(Layer *layer, GContext *ctx) {
  GRect b = layer_get_bounds(layer);
  graphics_context_set_fill_color(ctx, GColorBlack);
  graphics_fill_rect(ctx, b, 0, GCornerNone);
  time_t now = time(NULL);
  struct tm now_tm = *localtime(&now);
  struct tm *tm = &now_tm;
  int y = PBL_IF_ROUND_ELSE(22, 2);

  if (s_alert[0]) {   // only for admins (the Spark sends it only to them)
    graphics_context_set_fill_color(ctx, PBL_IF_COLOR_ELSE(GColorRed, GColorWhite));
    graphics_fill_rect(ctx, GRect(0, y, b.size.w, 22), 0, GCornerNone);
    graphics_context_set_text_color(ctx, PBL_IF_COLOR_ELSE(GColorWhite, GColorBlack));
    graphics_draw_text(ctx, s_alert, fonts_get_system_font(FONT_KEY_GOTHIC_14_BOLD),
                       GRect(PBL_IF_ROUND_ELSE(30, 4), y + 2, b.size.w - PBL_IF_ROUND_ELSE(60, 8), 20),
                       GTextOverflowModeTrailingEllipsis, GTextAlignmentCenter, NULL);
    y += 24;
  }

  static char clock[8], date[40];
  strftime(clock, sizeof(clock), clock_is_24h_style() ? "%H:%M" : "%I:%M", tm);
  snprintf(date, sizeof(date), "%s %d.%d.%s", DAYS[tm->tm_wday], tm->tm_mday, tm->tm_mon + 1, s_where_out ? " · unterwegs" : "");
  graphics_context_set_text_color(ctx, GColorWhite);
  graphics_draw_text(ctx, clock, fonts_get_system_font(FONT_KEY_LECO_42_NUMBERS), GRect(0, y, b.size.w, 50),
                     GTextOverflowModeFill, GTextAlignmentCenter, NULL);
  y += 50;
  graphics_context_set_text_color(ctx, PBL_IF_COLOR_ELSE(GColorVividCerulean, GColorWhite));
  graphics_draw_text(ctx, date, fonts_get_system_font(FONT_KEY_GOTHIC_18_BOLD), GRect(0, y, b.size.w, 22),
                     GTextOverflowModeFill, GTextAlignmentCenter, NULL);
  y += 26;

  GFont f = fonts_get_system_font(FONT_KEY_GOTHIC_18);
  static char buf[TEXT_LEN + 24], when[24];
  if (s_next[0]) {
    if (s_next_t > 0) {
      when_text(when, sizeof(when), s_next_t);
      snprintf(buf, sizeof(buf), "%s %s", when, s_next);
    } else {
      snprintf(buf, sizeof(buf), "%s", s_next);
    }
    y = line(ctx, b, y, icon_calendar, buf, f);
  }
  if (s_rem[0] && s_rem_t > (int32_t)now - 60) {
    when_text(when, sizeof(when), s_rem_t);
    snprintf(buf, sizeof(buf), "%s %s", when, s_rem);
    y = line(ctx, b, y, icon_bell, buf, f);
  }
  if (s_wx[0]) y = line(ctx, b, y, icon_sun, s_wx, f);
  const char *foot = s_status[0] ? s_status : s_tip;
  if (foot[0] && y < b.size.h - PBL_IF_ROUND_ELSE(40, 20)) {
    graphics_context_set_text_color(ctx, PBL_IF_COLOR_ELSE(GColorLightGray, GColorWhite));
    graphics_draw_text(ctx, foot, fonts_get_system_font(FONT_KEY_GOTHIC_14),
                       GRect(PBL_IF_ROUND_ELSE(40, 6), b.size.h - PBL_IF_ROUND_ELSE(44, 20), b.size.w - PBL_IF_ROUND_ELSE(80, 12), 18),
                       GTextOverflowModeTrailingEllipsis, GTextAlignmentCenter, NULL);
  }
}

// ---------------------------------------------------------------- the phone

static void refresh(void) {
  DictionaryIterator *it;
  if (app_message_outbox_begin(&it) != APP_MSG_OK) {
    s_refresh_pending = true;
    return;
  }
  dict_write_int32(it, MESSAGE_KEY_REFRESH, 1);
  if (app_message_outbox_send() == APP_MSG_OK) s_refresh_pending = false;
}

static void sent(DictionaryIterator *it, void *ctx) {
  if (s_refresh_pending) refresh();
}

static void failed(DictionaryIterator *it, AppMessageResult reason, void *ctx) {
  s_refresh_pending = false;   // the next quarter of an hour tries again
}

static void inbox(DictionaryIterator *it, void *ctx) {
  Tuple *t;
  if ((t = dict_find(it, MESSAGE_KEY_NEXT_T))) {
    s_next_t = t->value->int32;
    persist_write_int(P_NEXT_T, s_next_t);
  }
  if ((t = dict_find(it, MESSAGE_KEY_NEXT))) keep(P_NEXT, s_next, t->value->cstring);
  if ((t = dict_find(it, MESSAGE_KEY_REM_T))) {
    s_rem_t = t->value->int32;
    persist_write_int(P_REM_T, s_rem_t);
  }
  if ((t = dict_find(it, MESSAGE_KEY_REM))) keep(P_REM, s_rem, t->value->cstring);
  if ((t = dict_find(it, MESSAGE_KEY_WX))) keep(P_WX, s_wx, t->value->cstring);
  if ((t = dict_find(it, MESSAGE_KEY_TIP))) keep(P_TIP, s_tip, t->value->cstring);
  if ((t = dict_find(it, MESSAGE_KEY_ALERT))) {
    const char *v = t->value->cstring;
    bool fresh = strlen(v) > 0 && strcmp(v, s_alert) != 0;
    keep(P_ALERT, s_alert, t->value->cstring);
    if (fresh) vibes_double_pulse();   // a new outage: once, not every quarter of an hour
  }
  if ((t = dict_find(it, MESSAGE_KEY_WHERE))) {
    s_where_out = t->value->int32 != 0;
    persist_write_bool(P_WHERE, s_where_out);
  }
  if ((t = dict_find(it, MESSAGE_KEY_STATUS))) snprintf(s_status, sizeof(s_status), "%s", t->value->cstring);
  else s_status[0] = 0;
  layer_mark_dirty(s_layer);
}

static void tick(struct tm *tm, TimeUnits changed) {
  if (tm->tm_min % REFRESH_MIN == 0) refresh();
  layer_mark_dirty(s_layer);
}

// ---------------------------------------------------------------- start and end

static void win_load(Window *w) {
  Layer *root = window_get_root_layer(w);
  s_layer = layer_create(layer_get_bounds(root));
  layer_set_update_proc(s_layer, draw);
  layer_add_child(root, s_layer);
}

static void win_unload(Window *w) {
  layer_destroy(s_layer);
}

static void init(void) {
  load();
  s_window = window_create();
  window_set_window_handlers(s_window, (WindowHandlers){.load = win_load, .unload = win_unload});
  window_stack_push(s_window, false);
  app_message_register_inbox_received(inbox);
  app_message_register_outbox_sent(sent);
  app_message_register_outbox_failed(failed);
  app_message_open(512, 64);
  tick_timer_service_subscribe(MINUTE_UNIT, tick);
}

static void deinit(void) {
  tick_timer_service_unsubscribe();
  window_destroy(s_window);
}

int main(void) {
  init();
  app_event_loop();
  deinit();
}
