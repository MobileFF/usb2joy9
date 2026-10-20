#ifndef PORT_H_
#define PORT_H_

#include <stdbool.h>

// 9ピン側に出す状態 (true = 押下)
typedef struct {
  bool up, down, left, right;
  bool a, b;      // MSX: トリガA/B、MD: A/B
  bool c, start;  // MD のみ
} port_state_t;

// 出力回路
//   0: 74LVC07A (オープンドレインバッファ)  … GPIO=L で押下 / H で離す
//   1: NPN トランジスタ / N-ch MOSFET      … GPIO=H で押下 / L で離す
//   2: FXMA108 (双方向レベル変換)           … GPIO=L で押下 / H で離す + /OE を L に
#define OUT_74LVC07  0
#define OUT_NPN      1
#define OUT_FXMA108  2

#ifndef OUT_MODE
#define OUT_MODE OUT_74LVC07
#endif

#define PIN_OE     8   // FXMA108 の /OE (L で有効、OUT_MODE 2 のときのみ使用)

#if JOY_TARGET_MD
// Pico の GPIO とメガドライブのコントローラ端子の対応
#define PIN_UP     2   // MD pin 1
#define PIN_DOWN   3   // MD pin 2
#define PIN_LEFT   4   // MD pin 3
#define PIN_RIGHT  5   // MD pin 4
#define PIN_TL     6   // MD pin 6 (A / B)
#define PIN_TR     7   // MD pin 9 (C / Start)
#define PIN_TH     9   // MD pin 7 (本体からのセレクト信号、入力)
#else
// Pico の GPIO と MSX ジョイスティックポートの対応
#define PIN_UP     2   // MSX pin 1
#define PIN_DOWN   3   // MSX pin 2
#define PIN_LEFT   4   // MSX pin 3
#define PIN_RIGHT  5   // MSX pin 4
#define PIN_TRG_A  6   // MSX pin 6
#define PIN_TRG_B  7   // MSX pin 7
#endif

void port_init(void);
void port_write(const port_state_t *s);

#endif
