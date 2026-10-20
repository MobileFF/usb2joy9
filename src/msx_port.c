#include "port.h"

#include "hardware/gpio.h"

#define PIN_MASK ((1u << PIN_UP) | (1u << PIN_DOWN) | (1u << PIN_LEFT) | \
                  (1u << PIN_RIGHT) | (1u << PIN_TRG_A) | (1u << PIN_TRG_B))

void port_init(void) {
  gpio_init_mask(PIN_MASK);
  gpio_put_masked(PIN_MASK, OUT_MODE == OUT_NPN ? 0 : PIN_MASK);  // 全部離した状態
  gpio_set_dir_out_masked(PIN_MASK);

#if OUT_MODE == OUT_FXMA108
  // FXMA108 はバスホールド付きなので内蔵プルを切り、push-pull で駆動する。
  for (uint pin = 0; pin < 32; pin++) {
    if (PIN_MASK & (1u << pin)) gpio_disable_pulls(pin);
  }
  // /OE は L で有効。出力を確定させてから有効にする (起動時の誤入力防止)
  gpio_init(PIN_OE);
  gpio_put(PIN_OE, 0);
  gpio_set_dir(PIN_OE, GPIO_OUT);
#endif
}

void port_write(const port_state_t *s) {
  uint32_t pressed = (s->up ? 1u << PIN_UP : 0) | (s->down ? 1u << PIN_DOWN : 0) |
                     (s->left ? 1u << PIN_LEFT : 0) | (s->right ? 1u << PIN_RIGHT : 0) |
                     (s->a ? 1u << PIN_TRG_A : 0) | (s->b ? 1u << PIN_TRG_B : 0);
  gpio_put_masked(PIN_MASK, OUT_MODE == OUT_NPN ? pressed : ~pressed);
}
