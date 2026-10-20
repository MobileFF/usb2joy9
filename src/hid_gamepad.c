// 汎用 HID ゲームパッド用の軽量レポートディスクリプタパーサ
#include "hid_gamepad.h"

#include <string.h>

#define USAGE(page, id)    (((uint32_t)(page) << 16) | (id))
#define GD_JOYSTICK        USAGE(0x01, 0x04)
#define GD_GAMEPAD         USAGE(0x01, 0x05)
#define GD_MULTIAXIS       USAGE(0x01, 0x08)
#define GD_X               USAGE(0x01, 0x30)
#define GD_Y               USAGE(0x01, 0x31)
#define GD_HAT             USAGE(0x01, 0x39)
#define GD_DPAD_UP         USAGE(0x01, 0x90)
#define GD_DPAD_LEFT       USAGE(0x01, 0x93)
#define PAGE_BUTTON        0x09

#define MAX_LOCAL_USAGES   16
#define MAX_REPORT_IDS     8

static void set_field(hid_field_t *f, uint8_t rid, uint16_t off, uint8_t size,
                      int32_t lmin, int32_t lmax) {
  if (f->valid) return;  // 最初に見つかったものを優先
  f->valid = true;
  f->rid   = rid;
  f->off   = off;
  f->size  = size;
  f->lmin  = lmin;
  f->lmax  = lmax;
  f->sgn   = lmin < 0;
}

static bool assign(gp_layout_t *L, uint32_t usage, uint8_t rid, uint16_t off,
                   uint8_t size, int32_t lmin, int32_t lmax) {
  hid_field_t *f = NULL;
  if (usage == GD_X) {
    f = &L->x;
  } else if (usage == GD_Y) {
    f = &L->y;
  } else if (usage == GD_HAT) {
    f = &L->hat;
  } else if (usage >= GD_DPAD_UP && usage <= GD_DPAD_LEFT) {
    f = &L->dpad[usage - GD_DPAD_UP];
  } else if ((usage >> 16) == PAGE_BUTTON) {
    uint16_t n = usage & 0xFFFF;
    if (n >= 1 && n <= GP_MAX_BUTTONS) f = &L->btn[n - 1];
  }
  if (!f) return false;
  set_field(f, rid, off, size, lmin, lmax);
  return true;
}

bool gp_parse(gp_layout_t *L, const uint8_t *d, uint16_t len) {
  memset(L, 0, sizeof(*L));

  // グローバル項目
  uint16_t upage = 0;
  int32_t  lmin = 0, lmax = 0;
  uint32_t rsize = 0, rcount = 0;
  uint8_t  rid = 0;
  // ローカル項目
  uint32_t usages[MAX_LOCAL_USAGES];
  uint8_t  nus = 0;
  uint32_t umin = 0, umax = 0;
  bool     has_range = false;
  // コレクション
  uint8_t  depth = 0;
  uint32_t app = 0;
  // レポートIDごとのビット位置
  struct { uint8_t id; uint16_t off; } offs[MAX_REPORT_IDS] = {{0, 0}};
  uint8_t noffs = 1;

  bool found = false;
  uint16_t i = 0;

  while (i < len) {
    uint8_t p = d[i++];
    if (p == 0xFE) {  // long item
      if (i >= len) break;
      i += 2 + d[i];
      continue;
    }
    uint8_t sz = p & 3;
    if (sz == 3) sz = 4;
    if (i + sz > len) break;

    uint32_t u = 0;
    for (uint8_t k = 0; k < sz; k++) u |= (uint32_t)d[i + k] << (8 * k);
    int32_t s = (int32_t)u;
    if (sz == 1) s = (int8_t)u;
    else if (sz == 2) s = (int16_t)u;
    i += sz;

    uint8_t type = (p >> 2) & 3;
    uint8_t tag  = p >> 4;

    switch (type) {
      case 0:  // Main
        if (tag == 0xA) {  // Collection
          if (depth == 0 && u == 0x01) {  // Application
            app = nus ? usages[0] : (has_range ? umin : 0);
          }
          depth++;
        } else if (tag == 0xC) {  // End Collection
          if (depth) depth--;
        } else if (tag == 0x8) {  // Input
          uint8_t slot = 0;
          while (slot < noffs && offs[slot].id != rid) slot++;
          if (slot == noffs) {
            if (noffs < MAX_REPORT_IDS) {
              offs[noffs].id  = rid;
              offs[noffs].off = 0;
              noffs++;
            } else {
              slot = noffs - 1;
            }
          }
          uint16_t off = offs[slot].off;
          bool is_pad = app == GD_JOYSTICK || app == GD_GAMEPAD || app == GD_MULTIAXIS;
          if (is_pad && !(u & 1) && rsize > 0 && rsize <= 32) {  // Data (非 Constant)
            for (uint32_t c = 0; c < rcount; c++) {
              uint32_t us = 0;
              if (nus) {
                us = usages[c < nus ? c : (uint32_t)nus - 1];
              } else if (has_range && umin + c <= umax) {
                us = umin + c;
              }
              if (us && assign(L, us, rid, off + c * rsize, rsize, lmin, lmax)) found = true;
            }
          }
          offs[slot].off = off + rsize * rcount;
        }
        nus = 0;
        has_range = false;
        break;

      case 1:  // Global
        switch (tag) {
          case 0x0: upage = u; break;
          case 0x1: lmin = s; break;
          case 0x2: lmax = (lmin >= 0 && s < lmin) ? (int32_t)u : s; break;
          case 0x7: rsize = u; break;
          case 0x8: rid = u; L->has_rid = true; break;
          case 0x9: rcount = u; break;
          default: break;
        }
        break;

      case 2: {  // Local
        uint32_t full = (sz == 4) ? u : USAGE(upage, u);
        if (tag == 0x0) {
          if (nus < MAX_LOCAL_USAGES) usages[nus++] = full;
        } else if (tag == 0x1) {
          umin = full;
          has_range = true;
        } else if (tag == 0x2) {
          umax = full;
        }
        break;
      }

      default:
        break;
    }
  }
  return found;
}

static bool get_field(const hid_field_t *f, const uint8_t *r, uint16_t len, uint8_t rid, int32_t *v) {
  if (!f->valid || f->rid != rid) return false;
  if ((uint32_t)f->off + f->size > (uint32_t)len * 8) return false;

  uint32_t x = 0;
  for (uint8_t b = 0; b < f->size; b++) {
    uint16_t bit = f->off + b;
    if (r[bit >> 3] & (1u << (bit & 7))) x |= 1u << b;
  }
  if (f->sgn && f->size < 32 && (x & (1u << (f->size - 1)))) {
    x |= ~0u << f->size;
  }
  *v = (int32_t)x;
  return true;
}

// 軸の値を -1 / 0 / +1 に (範囲の両端 1/4 で ON)
static int axis_dir(const hid_field_t *f, int32_t v) {
  int32_t range = f->lmax - f->lmin;
  if (range <= 0) return 0;
  if (v < f->lmin + range / 4) return -1;
  if (v > f->lmax - range / 4) return 1;
  return 0;
}

bool gp_decode(const gp_layout_t *L, const uint8_t *r, uint16_t len, gp_state_t *st) {
  uint8_t rid = 0;
  if (L->has_rid) {
    if (len == 0) return false;
    rid = r[0];
    r++;
    len--;
  }

  gp_state_t s = {0};
  bool hit = false;
  int32_t v;

  if (get_field(&L->x, r, len, rid, &v)) {
    int dir = axis_dir(&L->x, v);
    s.left  = dir < 0;
    s.right = dir > 0;
    hit = true;
  }
  if (get_field(&L->y, r, len, rid, &v)) {
    int dir = axis_dir(&L->y, v);
    s.up   = dir < 0;
    s.down = dir > 0;
    hit = true;
  }
  if (get_field(&L->hat, r, len, rid, &v)) {
    int32_t n = v - L->hat.lmin;
    int32_t range = L->hat.lmax - L->hat.lmin;
    if (range == 7 && n >= 0 && n <= 7) {  // 8方向: 0=上 から時計回り
      static const uint8_t dirs8[8] = {0x1, 0x9, 0x8, 0xA, 0x2, 0x6, 0x4, 0x5};
      uint8_t m = dirs8[n];  // bit0=上 bit1=下 bit2=左 bit3=右
      s.up |= m & 1; s.down |= (m >> 1) & 1; s.left |= (m >> 2) & 1; s.right |= (m >> 3) & 1;
    } else if (range == 3 && n >= 0 && n <= 3) {  // 4方向
      s.up |= n == 0; s.right |= n == 1; s.down |= n == 2; s.left |= n == 3;
    }
    hit = true;
  }
  bool *dp[4] = {&s.up, &s.down, &s.right, &s.left};
  for (int k = 0; k < 4; k++) {
    if (get_field(&L->dpad[k], r, len, rid, &v)) {
      *dp[k] |= v != 0;
      hit = true;
    }
  }
  for (int k = 0; k < GP_MAX_BUTTONS; k++) {
    if (get_field(&L->btn[k], r, len, rid, &v)) {
      if (v) s.buttons |= 1u << k;
      hit = true;
    }
  }

  if (hit) *st = s;
  return hit;
}

// キーボード: 矢印/テンキー8246 で方向、Space/Z = ボタン1、X/M = ボタン2、C = ボタン3、Enter = ボタン10
void gp_decode_keyboard(const uint8_t *r, uint16_t len, gp_state_t *st) {
  gp_state_t s = {0};
  for (uint16_t k = 2; k < len && k < 8; k++) {
    switch (r[k]) {
      case 0x52: case 0x60: s.up = true; break;     // ↑ / KP8
      case 0x51: case 0x5A: s.down = true; break;   // ↓ / KP2
      case 0x50: case 0x5C: s.left = true; break;   // ← / KP4
      case 0x4F: case 0x5E: s.right = true; break;  // → / KP6
      case 0x2C: case 0x1D: s.buttons |= 0x1; break;  // Space / Z
      case 0x1B: case 0x10: s.buttons |= 0x2; break;  // X / M
      case 0x06: s.buttons |= 0x4; break;             // C
      case 0x28: s.buttons |= 0x200; break;           // Enter (Button 10)
      default: break;
    }
  }
  *st = s;
}
