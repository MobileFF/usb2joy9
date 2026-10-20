#ifndef HID_GAMEPAD_H_
#define HID_GAMEPAD_H_

#include <stdbool.h>
#include <stdint.h>

#define GP_MAX_BUTTONS 16

// レポート内の1フィールドの位置 (レポートID の直後を bit 0 とする)
typedef struct {
  bool     valid;
  bool     sgn;
  uint8_t  rid;
  uint8_t  size;
  uint16_t off;
  int32_t  lmin, lmax;
} hid_field_t;

// HID レポートディスクリプタから取り出したゲームパッドの配置
typedef struct {
  bool        has_rid;
  hid_field_t x, y, hat;
  hid_field_t dpad[4];              // GD D-pad Up/Down/Right/Left (0x90-0x93)
  hid_field_t btn[GP_MAX_BUTTONS];  // Button 1..16
} gp_layout_t;

typedef struct {
  bool     up, down, left, right;
  uint16_t buttons;                 // bit0 = Button 1
} gp_state_t;

// ジョイスティック/ゲームパッドの入力が見つかれば true
bool gp_parse(gp_layout_t *L, const uint8_t *desc, uint16_t len);

// 該当するレポートなら *st を更新して true
bool gp_decode(const gp_layout_t *L, const uint8_t *report, uint16_t len, gp_state_t *st);

// ブートプロトコルのキーボードレポート (8バイト) を変換
void gp_decode_keyboard(const uint8_t *report, uint16_t len, gp_state_t *st);

#endif
