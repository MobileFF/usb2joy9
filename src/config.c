#include "config.h"

#include <string.h>

uint32_t config_crc32(const uint8_t *data, uint32_t len) {
  uint32_t crc = 0xFFFFFFFFu;
  for (uint32_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (int b = 0; b < 8; b++) crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1));
  }
  return ~crc;
}

static uint32_t rd32(const uint8_t *p) {
  return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24);
}

void config_default(uint8_t target, config_t *cfg) {
  memset(cfg, 0, sizeof(*cfg));
  cfg->target = target;
  cfg->turbo_hz = 15;
  cfg->flags = CFG_FLAG_CANCEL_OPPOSITE;
  cfg->button_action[0] = ACT_A;
  cfg->button_action[1] = ACT_B;
  if (target == CFG_TARGET_MD) {
    cfg->button_action[2] = ACT_C;
    cfg->button_action[9] = ACT_START;  // 多くのパッドで Button 10 = Start
  } else {
    cfg->button_action[2] = ACT_TURBO_A;
    cfg->button_action[3] = ACT_TURBO_B;
  }
}

bool config_parse(const uint8_t *block, uint8_t target, config_t *cfg) {
  if (rd32(block) != CFG_MAGIC) return false;
  if (block[4] != CFG_VERSION) return false;
  if (rd32(block + CFG_BLOCK_SIZE - 4) != config_crc32(block, CFG_BLOCK_SIZE - 4)) return false;
  if (block[5] != target) return false;  // 別の機種用の設定は使わない

  config_t c;
  c.target = block[5];
  c.turbo_hz = block[6];
  if (c.turbo_hz < 1 || c.turbo_hz > 30) c.turbo_hz = 15;
  c.flags = block[7];
  for (int i = 0; i < CFG_NUM_BUTTONS; i++) {
    uint8_t a = block[8 + i];
    c.button_action[i] = a < ACT_COUNT ? a : ACT_NONE;
  }
  *cfg = c;
  return true;
}
