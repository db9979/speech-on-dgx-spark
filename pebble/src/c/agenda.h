#pragma once
#include <pebble.h>

// Reminders, timers and quick commands kept on the watch (watch app 2.0, plan pebble-ideen/plan.md).
// The phone sends the profile's next reminders (AGENDA) and quick commands (QUICK); the watch keeps them in
// persistent storage and schedules a wake-up for each reminder, so it rings without the phone.

typedef void (*AgendaAskFn)(const char *text);

// actions that go back to the Spark (pkjs turns the number into the word)
enum { ActPlayed = 0, ActSnooze = 1, ActStop = 2, ActPlus = 3, ActCancel = 4 };

void agenda_init(AgendaAskFn ask, void (*out_ready)(void));
void agenda_deinit(void);
// true when the app was started by a reminder's wake-up (its alert is on screen then)
bool agenda_launch(void);

void agenda_set(const char *lines);   // "id|due|made|rep|text" per line; "" = none
void agenda_off(void);                // the admin switched it off: no wake-ups
void quick_set(const char *lines);    // one command per line; "\x01" + letter + title is a fixed entry (T, W, M)

void agenda_show_list(void);
void quick_show_list(void);

// the next reminder action for the phone (main.c sends it through its one outbox)
bool agenda_out_peek(char *id, size_t id_len, int32_t *act, char *text, size_t text_len);
void agenda_out_sent(void);

// the black bar on the right of the alert, the timer and the confirmation: symbols 0 ✓, 1 zZ, 2 ✕, 3 +, 4 ■, -1 none
void agenda_draw_bar(GContext *ctx, GRect bounds, int up, int mid, int down);
