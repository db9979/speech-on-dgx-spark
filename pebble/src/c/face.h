// The assistant's face on the watch. All drawing lives in face.c, so a new face design only
// replaces that file; the app talks to it through these few calls.
#pragma once
#include <pebble.h>

typedef enum {
  FaceIdle = 0,   // waiting for a question
  FaceListen,     // dictation running
  FaceThink,      // waiting for the answer
  FaceSpeak,      // answer playing; mouth follows face_set_level()
  FaceSad,        // something went wrong
} FaceMode;

Layer *face_create(GRect frame);
void face_destroy(void);
void face_set_mode(FaceMode mode);
// Loudness of what is playing right now, 0 (silent) to 255.
void face_set_level(uint8_t level);
