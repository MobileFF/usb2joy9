// USB ジョイスティック / キーボード → MSX / メガドライブ 9ピンポート変換
#include <stdio.h>
#include <string.h>

#include "pico/stdlib.h"
#include "hardware/structs/usb.h"
#include "tusb.h"

#include "config.h"
#include "hid_gamepad.h"
#include "port.h"

#if JOY_TARGET_MD
#define TARGET      CFG_TARGET_MD
#define TARGET_NAME "usb2mdjoy"
#else
#define TARGET      CFG_TARGET_MSX
#define TARGET_NAME "usb2msxjoy"
#endif

// 設定ブロックはフラッシュ末尾 4KB セクタの先頭に置く
#define CFG_FLASH_OFFSET (PICO_FLASH_SIZE_BYTES - 4096)

static config_t cfg;

enum { KIND_NONE, KIND_PAD, KIND_KEYBOARD };

typedef struct {
  uint8_t     kind;
  uint8_t     dev_addr;
  uint8_t     idx;
  gp_layout_t layout;
  gp_state_t  state;
} hid_slot_t;

static hid_slot_t slots[CFG_TUH_HID];
static int usb_devices;  // エニュメレーションが完了した USB 機器の数

void tuh_mount_cb(uint8_t dev_addr) {
  uint16_t vid = 0, pid = 0;
  tuh_vid_pid_get(dev_addr, &vid, &pid);
  printf("USB mount: addr=%u %04x:%04x\n", dev_addr, vid, pid);
  usb_devices++;
}

void tuh_umount_cb(uint8_t dev_addr) {
  printf("USB unmount: addr=%u\n", dev_addr);
  if (usb_devices > 0) usb_devices--;
}

static hid_slot_t *find_slot(uint8_t dev_addr, uint8_t idx) {
  for (int i = 0; i < CFG_TUH_HID; i++) {
    if (slots[i].kind != KIND_NONE && slots[i].dev_addr == dev_addr && slots[i].idx == idx) {
      return &slots[i];
    }
  }
  return NULL;
}

static hid_slot_t *alloc_slot(void) {
  for (int i = 0; i < CFG_TUH_HID; i++) {
    if (slots[i].kind == KIND_NONE) return &slots[i];
  }
  return NULL;
}

void tuh_hid_mount_cb(uint8_t dev_addr, uint8_t idx, uint8_t const *desc, uint16_t desc_len) {
  uint16_t vid = 0, pid = 0;
  tuh_vid_pid_get(dev_addr, &vid, &pid);
  uint8_t proto = tuh_hid_interface_protocol(dev_addr, idx);
  printf("HID mount: addr=%u idx=%u %04x:%04x proto=%u desc=%u\n", dev_addr, idx, vid, pid, proto, desc_len);

  hid_slot_t *s = alloc_slot();
  if (!s) return;
  memset(s, 0, sizeof(*s));
  s->dev_addr = dev_addr;
  s->idx = idx;

  if (proto == HID_ITF_PROTOCOL_KEYBOARD) {
    s->kind = KIND_KEYBOARD;
  } else if (proto == HID_ITF_PROTOCOL_NONE && gp_parse(&s->layout, desc, desc_len)) {
    s->kind = KIND_PAD;
    printf("  gamepad: X=%d Y=%d hat=%d rid=%d\n", s->layout.x.valid, s->layout.y.valid,
           s->layout.hat.valid, s->layout.has_rid);
  } else {
    printf("  ignored\n");
    return;  // マウスなど
  }

  tuh_hid_receive_report(dev_addr, idx);
}

void tuh_hid_umount_cb(uint8_t dev_addr, uint8_t idx) {
  printf("HID unmount: addr=%u idx=%u\n", dev_addr, idx);
  hid_slot_t *s = find_slot(dev_addr, idx);
  if (s) s->kind = KIND_NONE;
}

void tuh_hid_report_received_cb(uint8_t dev_addr, uint8_t idx, uint8_t const *report, uint16_t len) {
  hid_slot_t *s = find_slot(dev_addr, idx);
  if (s) {
    uint16_t before = s->state.buttons;
    if (s->kind == KIND_KEYBOARD) {
      gp_decode_keyboard(report, len, &s->state);
    } else {
      gp_decode(&s->layout, report, len, &s->state);
    }
    // 設定ツールでの割り当て用に、新しく押されたボタンの番号を表示
    uint16_t pressed = s->state.buttons & ~before;
    for (int k = 0; k < CFG_NUM_BUTTONS; k++) {
      if (pressed >> k & 1) printf("button %d\n", k + 1);
    }
  }
  tuh_hid_receive_report(dev_addr, idx);
}

static void update_port(void) {
  gp_state_t m = {0};
  bool mounted = false;
  for (int i = 0; i < CFG_TUH_HID; i++) {
    if (slots[i].kind == KIND_NONE) continue;
    mounted = true;
    m.up      |= slots[i].state.up;
    m.down    |= slots[i].state.down;
    m.left    |= slots[i].state.left;
    m.right   |= slots[i].state.right;
    m.buttons |= slots[i].state.buttons;
  }

  port_state_t o = {
    .up = m.up, .down = m.down, .left = m.left, .right = m.right,
  };

  // スティックの上下・左右同時入力は打ち消す (誤動作するソフトがあるため)。
  // ボタンに割り当てた同時押しはこの後で加えるので打ち消されない。
  if (cfg.flags & CFG_FLAG_CANCEL_OPPOSITE) {
    if (o.up && o.down) o.up = o.down = false;
    if (o.left && o.right) o.left = o.right = false;
  }

  bool turbo_on = (time_us_32() / (500000 / cfg.turbo_hz)) & 1;
  for (int k = 0; k < CFG_NUM_BUTTONS; k++) {
    if (!(m.buttons >> k & 1)) continue;
    switch (cfg.button_action[k]) {
      case ACT_A:          o.a = true; break;
      case ACT_B:          o.b = true; break;
      case ACT_C:          o.c = true; break;
      case ACT_START:      o.start = true; break;
      case ACT_TURBO_A:    o.a |= turbo_on; break;
      case ACT_TURBO_B:    o.b |= turbo_on; break;
      case ACT_TURBO_C:    o.c |= turbo_on; break;
      case ACT_UP_DOWN:    o.up = o.down = true; break;
      case ACT_LEFT_RIGHT: o.left = o.right = true; break;
      case ACT_UP:         o.up = true; break;
      case ACT_DOWN:       o.down = true; break;
      case ACT_LEFT:       o.left = true; break;
      case ACT_RIGHT:      o.right = true; break;
      default: break;
    }
  }

  port_write(&o);

#ifdef PICO_DEFAULT_LED_PIN
  // LED で接続の段階を表示する
  //   1Hz 点滅     : USB 機器が電気的に検出されない (電源・アダプタ・配線)
  //   5Hz 点滅     : 検出したがエニュメレーション未完了
  //   2回点滅/1秒  : エニュメレーション完了、使える HID がない
  //   点灯         : HID 機器を使用中
  uint32_t ms = time_us_32() / 1000;
  bool attached = usb_hw->sie_status & USB_SIE_STATUS_SPEED_BITS;
  bool led;
  if (mounted) {
    led = true;
  } else if (usb_devices > 0) {
    uint32_t t = ms % 1000;
    led = t < 100 || (t >= 200 && t < 300);
  } else if (attached) {
    led = (ms / 100) & 1;
  } else {
    led = (ms / 500) & 1;
  }
  gpio_put(PICO_DEFAULT_LED_PIN, led);
#else
  (void)mounted;
#endif
}

int main(void) {
  // 設定の読み込みは port_init より先に (MD ではコア1 が起動するため)
  const uint8_t *cfg_block = (const uint8_t *)(XIP_BASE + CFG_FLASH_OFFSET);
  bool cfg_ok = config_parse(cfg_block, TARGET, &cfg);
  if (!cfg_ok) config_default(TARGET, &cfg);

  port_init();  // 起動直後に「全ボタン離す」状態へ
  stdio_init_all();

#ifdef PICO_DEFAULT_LED_PIN
  gpio_init(PICO_DEFAULT_LED_PIN);
  gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);
#endif

  printf(TARGET_NAME " start (config: %s)\n", cfg_ok ? "flash" : "default");
  extern char __flash_binary_end;
  if ((uintptr_t)&__flash_binary_end > XIP_BASE + CFG_FLASH_OFFSET) {
    printf("WARNING: firmware overlaps the config sector\n");
  }
  tuh_init(BOARD_TUH_RHPORT);

  while (true) {
    tuh_task();
    update_port();
  }
}
