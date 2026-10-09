// The two faces the panel offers (chat.face): the robot (a rounded head with two eyes and a mouth)
// and the comic face, drawn after COMIC in app/panel/static/js/face.js. Keep the functions from face.h.
#include "face.h"
#include "comic_shapes.h"

#define FRAME_MS 80      // animation while thinking or speaking
#define BLINK_MS 150
#define BLINK_EVERY_MS 3600

static Layer *s_layer;
static AppTimer *s_timer;
static FaceMode s_mode = FaceIdle;
static int s_level, s_target;   // mouth opening, smoothed toward the audio level
static int s_frame;
static bool s_blink;
static int s_kind;              // 0 robot, 1 comic
static int s_gx, s_gy;          // comic: where the eyes look, -100 to 100

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
  // the comic face looks around now and then, like in the panel
  if (s_mode == FaceThink && s_frame % 18 == 0) {
    s_gx = 55 + rand() % 30;
    s_gy = -75 + rand() % 20;
  } else if ((s_mode == FaceIdle && !s_blink) || (s_mode == FaceSpeak && s_frame % 20 == 0)) {
    int wide = s_mode == FaceSpeak && rand() % 2 ? 80 : 40;
    s_gx = rand() % (wide + 1) - wide / 2;
    s_gy = rand() % (wide / 2 + 1) - wide / 4;
  } else if (s_mode == FaceListen || s_mode == FaceSad) {
    s_gx = 0;
    s_gy = s_mode == FaceSad ? 40 : 0;
  }
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

static void draw_robot(Layer *layer, GContext *ctx) {
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

// ---------------------------------------------------------------- comic face
// Points are in quarter units of the panel's 200 x 200 box; to_px maps them onto the layer.

#define COUNT(a) ((int)(sizeof(a) / sizeof((a)[0])))
#define COMIC_SKIN PBL_IF_COLOR_ELSE(GColorMelon, GColorWhite)
#define COMIC_LID PBL_IF_COLOR_ELSE(GColorRajah, GColorWhite)
#define COMIC_LINE GColorBlack

static GPoint s_pts[48];
static GPoint s_org;
static int s_size;   // pixels for 800 quarter units

static GPoint to_px(int x, int y) {
  return GPoint(s_org.x + x * s_size / 800, s_org.y + y * s_size / 800);
}

static int line_w(int units) {   // a stroke of the panel drawing (in quarter units), at least 1 px
  int w = units * s_size / 800;
  return w < 1 ? 1 : w;
}

static void fill_pts(GContext *ctx, int n, GColor fill, bool outline) {
  GPath path = {.num_points = n, .points = s_pts, .rotation = 0, .offset = GPointZero};
  graphics_context_set_fill_color(ctx, fill);
  gpath_draw_filled(ctx, &path);
  if (outline) {
    graphics_context_set_stroke_color(ctx, COMIC_LINE);
    graphics_context_set_stroke_width(ctx, line_w(8));
    gpath_draw_outline(ctx, &path);
  }
}

static void shape(GContext *ctx, const GPoint *src, int n, int dy, GColor fill, bool outline) {
  for (int i = 0; i < n && i < COUNT(s_pts); i++) s_pts[i] = to_px(src[i].x, src[i].y + dy);
  fill_pts(ctx, n < COUNT(s_pts) ? n : COUNT(s_pts), fill, outline);
}

// an ellipse, optionally cut off below y = cut (for the eye lids)
static int ellipse_pts(int cx, int cy, int rx, int ry, int cut) {
  const int n = 16;
  for (int k = 0; k < n; k++) {
    int32_t a = TRIG_MAX_ANGLE * k / n;
    int y = cy + ry * sin_lookup(a) / TRIG_MAX_RATIO;
    s_pts[k] = to_px(cx + rx * cos_lookup(a) / TRIG_MAX_RATIO, y < cut ? y : cut);
  }
  return n;
}

// a quadratic curve as a polyline
static int quad_pts(int start, int x0, int y0, int x1, int y1, int x2, int y2) {
  const int n = 6;
  for (int k = 0; k <= n; k++) {
    int u = n - k;
    s_pts[start + k] = to_px((u * u * x0 + 2 * u * k * x1 + k * k * x2) / (n * n),
                             (u * u * y0 + 2 * u * k * y1 + k * k * y2) / (n * n));
  }
  return start + n + 1;
}

static void polyline(GContext *ctx, int n, GColor color, int width) {
  graphics_context_set_stroke_color(ctx, color);
  graphics_context_set_stroke_width(ctx, width);
  for (int i = 1; i < n; i++) graphics_draw_line(ctx, s_pts[i - 1], s_pts[i]);
}

static void draw_comic(Layer *layer, GContext *ctx) {
  GRect b = layer_get_bounds(layer);
  int side = b.size.w < b.size.h ? b.size.w : b.size.h;
  GPoint mid = grect_center_point(&b);
  s_size = side * 200 / 196;   // the ring (radius 96 + its line) fills the layer
  s_org = GPoint(mid.x - s_size / 2, mid.y - s_size / 2);
  graphics_context_set_antialiased(ctx, true);

  // how open the mouth is (0..100) and how the mood moves brows and lids
  int open = s_mode == FaceSpeak ? s_level * 130 / 255 : 0;
  if (open > 100) open = 100;
  int lid = 46, brow_l = 0, brow_r = 0, ang_l = 0, ang_r = 0;   // lid in %, brows in quarter units / degrees
  switch (s_mode) {
    case FaceListen: lid = 22; brow_l = brow_r = -12; ang_l = ang_r = -3; break;
    case FaceThink: lid = 42; brow_l = -18; brow_r = 4; ang_l = -6; ang_r = 4; break;
    case FaceSpeak: lid = 30; brow_l = brow_r = -4 - (open > 80 ? 9 : 0) - open * 5 / 100; break;
    case FaceSad: lid = 54; brow_l = brow_r = -4; ang_l = ang_r = -9; break;
    default: break;
  }
  if (s_blink) lid = 100;

  // background, neck, shirt
  graphics_context_set_fill_color(ctx, PBL_IF_COLOR_ELSE(GColorCeleste, GColorWhite));
  graphics_fill_circle(ctx, to_px(400, 400), 96 * s_size / 200);
  shape(ctx, COMIC_NECK, COUNT(COMIC_NECK), 0, COMIC_SKIN, true);
  shape(ctx, COMIC_SHIRT, COUNT(COMIC_SHIRT), 0, PBL_IF_COLOR_ELSE(GColorIcterine, GColorWhite), true);

  // ears and head
  shape(ctx, COMIC_EAR_L, COUNT(COMIC_EAR_L), 0, COMIC_SKIN, true);
  shape(ctx, COMIC_EAR_R, COUNT(COMIC_EAR_R), 0, COMIC_SKIN, true);
  shape(ctx, COMIC_FACE, COUNT(COMIC_FACE), 0, COMIC_SKIN, true);

  // eyes: white, iris looking around, lid from above, brow
  for (int k = -1; k <= 1; k += 2) {
    int cx = 400 + k * 84, cy = 360, rx = 42, ry = 26;
    ellipse_pts(cx, cy, rx, ry, 10000);
    fill_pts(ctx, 16, GColorWhite, false);
    GPoint iris = to_px(cx + s_gx * rx * 45 / 10000, cy + s_gy * ry * 38 / 10000);
    int ir = 22 * s_size / 800;
    int max_r = ry * s_size / 800;
    graphics_context_set_fill_color(ctx, PBL_IF_COLOR_ELSE(GColorArmyGreen, GColorBlack));
    graphics_fill_circle(ctx, iris, ir < max_r ? ir : max_r);
    graphics_context_set_fill_color(ctx, GColorBlack);
    graphics_fill_circle(ctx, iris, ir / 2 > 0 ? ir / 2 : 1);
    if (lid > 0) {
      int cut = cy - ry - 4 + (2 * ry + 8) * lid / 100;
      ellipse_pts(cx, cy, rx + 2, ry + 2, cut);
      fill_pts(ctx, 16, COMIC_LID, false);
      graphics_context_set_stroke_color(ctx, COMIC_LINE);
      graphics_context_set_stroke_width(ctx, line_w(10));
      int half = rx * 9 / 10;
      graphics_draw_line(ctx, to_px(cx - half, cut), to_px(cx + half, cut));
    }
    ellipse_pts(cx, cy, rx, ry, 10000);
    GPath eye = {.num_points = 16, .points = s_pts, .rotation = 0, .offset = GPointZero};
    graphics_context_set_stroke_color(ctx, COMIC_LINE);
    graphics_context_set_stroke_width(ctx, line_w(7));
    gpath_draw_outline(ctx, &eye);

    // brow: a thick curve, raised and turned by the mood (rotate about its middle)
    int by = 306 + (k < 0 ? brow_l : brow_r);
    int ang = k * (k < 0 ? ang_l : ang_r);
    int32_t a = DEG_TO_TRIGANGLE(ang < 0 ? 360 + ang : ang);
    int s = sin_lookup(a), c = cos_lookup(a);
    int px[3] = {cx - k * 48, cx + k * 4, cx + k * 52}, py[3] = {by + 4, by - 20, by + 8};
    for (int i = 0; i < 3; i++) {
      int dx = px[i] - cx, dy = py[i] - by;
      px[i] = cx + (dx * c - dy * s) / TRIG_MAX_RATIO;
      py[i] = by + (dx * s + dy * c) / TRIG_MAX_RATIO;
    }
    int n = quad_pts(0, px[0], py[0], px[1], py[1], px[2], py[2]);
    polyline(ctx, n, GColorBlack, line_w(20) < 2 ? 2 : line_w(20));
  }

  // nose
  for (int i = 0; i < COUNT(COMIC_NOSE) && i < COUNT(s_pts); i++) s_pts[i] = to_px(COMIC_NOSE[i].x, COMIC_NOSE[i].y);
  polyline(ctx, COUNT(COMIC_NOSE), COMIC_LINE, line_w(9));

  // mouth under the mustache: a line, open while speaking, turned down when sad
  int my = 564, w = 32 * (100 - open * 15 / 100) / 100 + (s_mode == FaceSpeak ? 4 : 0);
  int o = open * 30 / 100;
  if (o > 2) {
    int n = quad_pts(0, 400 - w, my, 400, my - o * 35 / 100, 400 + w, my);
    n = quad_pts(n, 400 + w, my, 400, my + o * 2, 400 - w, my);
    fill_pts(ctx, n, PBL_IF_COLOR_ELSE(GColorBulgarianRose, GColorBlack), true);
  } else {
    int end = s_mode == FaceSad ? 6 : 0, bend = s_mode == FaceSad ? -6 : 2;
    int n = quad_pts(0, 400 - w, my + end, 400, my + bend, 400 + w, my + end);
    polyline(ctx, n, COMIC_LINE, line_w(9));
  }

  // short bushy mustache, lifted a little when the mouth opens, then the hair on top
  shape(ctx, COMIC_STACHE, COUNT(COMIC_STACHE), -open * 5 / 100, GColorBlack, false);
  shape(ctx, COMIC_HAIR, COUNT(COMIC_HAIR), 0, GColorBlack, false);

  // the ring shows the mood like in the panel
  GColor ring = PBL_IF_COLOR_ELSE(s_mode == FaceListen ? GColorPictonBlue : s_mode == FaceThink ? GColorChromeYellow
                                  : s_mode == FaceSpeak ? GColorJaegerGreen : s_mode == FaceSad ? GColorSunsetOrange
                                  : GColorLightGray, GColorBlack);
  graphics_context_set_stroke_color(ctx, ring);
  graphics_context_set_stroke_width(ctx, line_w(s_mode == FaceListen ? 32 : 20) < 2 ? 2 : line_w(s_mode == FaceListen ? 32 : 20));
  graphics_draw_circle(ctx, to_px(400, 400), 96 * s_size / 200);
}

static void update(Layer *layer, GContext *ctx) {
  if (s_kind == 1) draw_comic(layer, ctx);
  else draw_robot(layer, ctx);
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

void face_set_kind(int kind) {
  s_kind = kind == 1 ? 1 : 0;
  if (s_layer) layer_mark_dirty(s_layer);
}
