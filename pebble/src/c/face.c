// Face design: a rounded head with two eyes and a mouth. Replace this file to change the look;
// keep the functions from face.h.
#include "face.h"

#define FRAME_MS 80      // animation while thinking or speaking
#define BLINK_MS 150
#define BLINK_EVERY_MS 3600

static Layer *s_layer;
static AppTimer *s_timer;
static FaceMode s_mode = FaceIdle;
static int s_level, s_target;   // mouth opening, smoothed toward the audio level
static int s_frame;
static bool s_blink;

static void schedule(void);

static bool animated(void) {
  return s_mode == FaceThink || s_mode == FaceSpeak || s_level > 0;
}

static void tick(void *ctx) {
  s_timer = NULL;
  s_frame++;
  // fast attack, slower release, so the mouth reads as talking rather than flickering
  s_level = s_target > s_level ? (s_level + 3 * s_target) / 4 : (3 * s_level + s_target) / 4;
  if (s_mode != FaceSpeak) s_target = 0;
  s_blink = !animated() && s_mode == FaceIdle && !s_blink;
  layer_mark_dirty(s_layer);
  schedule();
}

static void schedule(void) {
  // between blinks the face sleeps, so an idle app costs next to nothing
  if (!s_timer) s_timer = app_timer_register(animated() ? FRAME_MS : s_blink ? BLINK_MS : BLINK_EVERY_MS, tick, NULL);
}

static void draw_eye(GContext *ctx, GPoint c, int w, int h, GPoint look, bool closed) {
  graphics_context_set_fill_color(ctx, GColorWhite);
  if (closed) {
    graphics_fill_rect(ctx, GRect(c.x - w / 2, c.y - 1, w, 3), 1, GCornersAll);
    return;
  }
  graphics_fill_rect(ctx, GRect(c.x - w / 2, c.y - h / 2, w, h), w / 2, GCornersAll);
  graphics_context_set_fill_color(ctx, PBL_IF_COLOR_ELSE(GColorOxfordBlue, GColorBlack));
  int p = w / 3;
  graphics_fill_circle(ctx, GPoint(c.x + look.x, c.y + look.y), p);
}

static void update(Layer *layer, GContext *ctx) {
  GRect b = layer_get_bounds(layer);
  int s = b.size.w < b.size.h ? b.size.w : b.size.h;
  GPoint mid = grect_center_point(&b);
  graphics_context_set_antialiased(ctx, true);

  // head
  int hw = s * 9 / 10, hh = s * 4 / 5;
  GRect head = GRect(mid.x - hw / 2, mid.y - hh / 2, hw, hh);
  graphics_context_set_fill_color(ctx, PBL_IF_COLOR_ELSE(
      s_mode == FaceSad ? GColorDarkCandyAppleRed : s_mode == FaceListen ? GColorCobaltBlue : GColorOxfordBlue,
      GColorBlack));
  graphics_fill_rect(ctx, head, hh / 3, GCornersAll);

  // eyes
  int ew = s / 6, eh = s * 9 / 40;
  int ey = mid.y - hh / 8;
  int ex = hw / 5;
  GPoint look = GPointZero;
  bool closed = false;
  if (s_mode == FaceThink) {
    look = GPoint(ew / 5, -eh / 4);                   // looking up to the side
  } else if (s_mode == FaceListen) {
    eh = eh * 5 / 4;                                   // wide awake
  } else if (s_mode == FaceSad) {
    look = GPoint(0, eh / 4);                          // looking down
  } else if (s_mode == FaceIdle) {
    closed = s_blink;
  }
  draw_eye(ctx, GPoint(mid.x - ex, ey), ew, eh, look, closed);
  draw_eye(ctx, GPoint(mid.x + ex, ey), ew, eh, look, closed);

  // mouth
  int my = mid.y + hh / 4;
  int mw = hw * 2 / 5;
  graphics_context_set_fill_color(ctx, GColorWhite);
  graphics_context_set_stroke_color(ctx, GColorWhite);
  graphics_context_set_stroke_width(ctx, s >= 80 ? 4 : 3);
  switch (s_mode) {
    case FaceSpeak: {
      int open = 4 + s_level * (hh / 4) / 255;
      graphics_fill_rect(ctx, GRect(mid.x - mw / 2, my - open / 2, mw, open), open / 2 < 6 ? open / 2 : 6,
                         GCornersAll);
      break;
    }
    case FaceListen:
      graphics_fill_circle(ctx, GPoint(mid.x, my), s / 16);
      break;
    case FaceThink:
      for (int i = 0; i < 3; i++) {
        int r = ((s_frame / 3) % 3) == i ? s / 22 : s / 34;
        graphics_fill_circle(ctx, GPoint(mid.x + (i - 1) * mw / 3, my), r);
      }
      break;
    case FaceSad:
      graphics_draw_arc(ctx, GRect(mid.x - mw / 2, my, mw, mw), GOvalScaleModeFitCircle,
                        DEG_TO_TRIGANGLE(-60), DEG_TO_TRIGANGLE(60));
      break;
    default:
      graphics_draw_arc(ctx, GRect(mid.x - mw / 2, my - mw * 3 / 4, mw, mw), GOvalScaleModeFitCircle,
                        DEG_TO_TRIGANGLE(120), DEG_TO_TRIGANGLE(240));
      break;
  }
}

Layer *face_create(GRect frame) {
  s_layer = layer_create(frame);
  layer_set_update_proc(s_layer, update);
  schedule();
  return s_layer;
}

void face_destroy(void) {
  if (s_timer) app_timer_cancel(s_timer);
  s_timer = NULL;
  layer_destroy(s_layer);
  s_layer = NULL;
}

static void restart(void) {
  if (s_timer) app_timer_cancel(s_timer);
  s_timer = NULL;
  if (s_layer) schedule();
}

void face_set_mode(FaceMode mode) {
  if (mode == s_mode) return;
  s_mode = mode;
  s_blink = false;
  if (s_layer) layer_mark_dirty(s_layer);
  restart();  // switch between the slow blink timer and the animation timer at once
}

void face_set_level(uint8_t level) {
  s_target = level;
}
