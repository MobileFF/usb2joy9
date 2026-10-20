// 配線確認用: GP2〜GP8 を H (3.3V) に固定し、LED を速く (5Hz) 点滅させるだけ
#include "pico/stdlib.h"

int main(void) {
  const uint32_t mask = 0x7Fu << 2;  // GP2〜GP8
  gpio_init_mask(mask);
  gpio_set_dir_out_masked(mask);
  gpio_set_mask(mask);

  gpio_init(PICO_DEFAULT_LED_PIN);
  gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);
  while (true) {
    gpio_xor_mask(1u << PICO_DEFAULT_LED_PIN);
    sleep_ms(100);
  }
}
