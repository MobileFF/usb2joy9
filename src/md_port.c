// メガドライブ 3ボタンパッドのエミュレーション
//
//   TH=H: pin1=上 pin2=下 pin3=左 pin4=右 pin6=B     pin9=C
//   TH=L: pin1=上 pin2=下 pin3=L   pin4=L   pin6=A     pin9=Start
//
// 本体は TH を切り替えて数µs後に読むので、コア1 を TH の監視専用にし、
// 2通りの出力値をコア0 があらかじめ用意しておく。
#include "port.h"

#include "hardware/gpio.h"
#include "hardware/structs/sio.h"
#include "pico/multicore.h"

#define PIN_MASK ((1u << PIN_UP) | (1u << PIN_DOWN) | (1u << PIN_LEFT) | \
                  (1u << PIN_RIGHT) | (1u << PIN_TL) | (1u << PIN_TR))

static volatile uint32_t out_th_high;
static volatile uint32_t out_th_low;

static uint32_t to_gpio(uint32_t pressed) {
  return OUT_MODE == OUT_NPN ? pressed : (~pressed & PIN_MASK);
}

// フラッシュの XIP キャッシュミスで止まらないよう RAM で実行する
static void __not_in_flash_func(core1_main)(void) {
  while (true) {
    uint32_t v = (sio_hw->gpio_in & (1u << PIN_TH)) ? out_th_high : out_th_low;
    sio_hw->gpio_togl = (sio_hw->gpio_out ^ v) & PIN_MASK;
  }
}

void port_init(void) {
  out_th_high = out_th_low = to_gpio(0);

  gpio_init_mask(PIN_MASK);
  gpio_put_masked(PIN_MASK, out_th_high);  // 全部離した状態
  gpio_set_dir_out_masked(PIN_MASK);

  gpio_init(PIN_TH);
  gpio_set_dir(PIN_TH, GPIO_IN);

#if OUT_MODE == OUT_FXMA108
  for (uint pin = 0; pin < 32; pin++) {
    if ((PIN_MASK | (1u << PIN_TH)) & (1u << pin)) gpio_disable_pulls(pin);
  }
  gpio_init(PIN_OE);
  gpio_put(PIN_OE, 0);
  gpio_set_dir(PIN_OE, GPIO_OUT);
#else
  gpio_pull_up(PIN_TH);  // 未接続時は TH=H 扱い
#endif

  multicore_launch_core1(core1_main);
}

void port_write(const port_state_t *s) {
  uint32_t dirs_ud = (s->up ? 1u << PIN_UP : 0) | (s->down ? 1u << PIN_DOWN : 0);

  uint32_t hi = dirs_ud | (s->left ? 1u << PIN_LEFT : 0) | (s->right ? 1u << PIN_RIGHT : 0) |
                (s->b ? 1u << PIN_TL : 0) | (s->c ? 1u << PIN_TR : 0);
  // TH=L では pin3/pin4 を L に固定 (本体はこれで 3ボタンパッドと判断する)
  uint32_t lo = dirs_ud | (1u << PIN_LEFT) | (1u << PIN_RIGHT) |
                (s->a ? 1u << PIN_TL : 0) | (s->start ? 1u << PIN_TR : 0);

  out_th_high = to_gpio(hi);
  out_th_low = to_gpio(lo);
}
