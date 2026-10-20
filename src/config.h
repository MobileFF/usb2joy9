#ifndef CONFIG_H_
#define CONFIG_H_

#include <stdbool.h>
#include <stdint.h>

// フラッシュ末尾 4KB セクタの先頭 256 バイトに置く設定ブロック。
// tools/config_gui が同じ形式の UF2 を生成する (形式を変えたら両方直すこと)。
//
//   off  size  内容
//   0    4     magic 'U2JC' (0x434A3255, little endian)
//   4    1     version (= 1)
//   5    1     target  (0 = MSX, 1 = メガドライブ)
//   6    1     turbo_hz (1〜30)
//   7    1     flags   (bit0: スティックの上下/左右同時入力を打ち消す)
//   8    16    button_action[16] (Button 1〜16 の動作 = cfg_action_t)
//   24   228   予約 (0)
//   252  4     CRC32 (offset 0〜251, zlib 互換)

#define CFG_MAGIC        0x434A3255u
#define CFG_VERSION      1
#define CFG_BLOCK_SIZE   256
#define CFG_NUM_BUTTONS  16

#define CFG_TARGET_MSX   0
#define CFG_TARGET_MD    1

#define CFG_FLAG_CANCEL_OPPOSITE 0x01

typedef enum {
  ACT_NONE = 0,
  ACT_A,           // MSX トリガA / MD A
  ACT_B,           // MSX トリガB / MD B
  ACT_TURBO_A,
  ACT_TURBO_B,
  ACT_UP_DOWN,     // 上下同時押し
  ACT_LEFT_RIGHT,  // 左右同時押し
  ACT_C,           // MD のみ
  ACT_START,       // MD のみ
  ACT_TURBO_C,     // MD のみ
  ACT_UP,
  ACT_DOWN,
  ACT_LEFT,
  ACT_RIGHT,
  ACT_COUNT
} cfg_action_t;

typedef struct {
  uint8_t target;
  uint8_t turbo_hz;
  uint8_t flags;
  uint8_t button_action[CFG_NUM_BUTTONS];
} config_t;

// ブロックを検証して *cfg に読み込む。不正なら false (cfg は変更しない)
bool config_parse(const uint8_t *block, uint8_t target, config_t *cfg);

// 既定値
void config_default(uint8_t target, config_t *cfg);

uint32_t config_crc32(const uint8_t *data, uint32_t len);

#endif
