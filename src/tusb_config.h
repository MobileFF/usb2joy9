#ifndef TUSB_CONFIG_H_
#define TUSB_CONFIG_H_

// CFG_TUSB_MCU / CFG_TUSB_OS は pico-sdk の tinyusb ターゲットが定義する

#ifndef CFG_TUSB_DEBUG
#define CFG_TUSB_DEBUG            0
#endif

#define CFG_TUH_MEM_SECTION
#define CFG_TUH_MEM_ALIGN         __attribute__ ((aligned(4)))

#define CFG_TUH_ENABLED           1
#define BOARD_TUH_RHPORT          0
#define CFG_TUH_MAX_SPEED         OPT_MODE_FULL_SPEED

#define CFG_TUH_ENUMERATION_BUFSIZE 512

// ハブ経由でキーボード+パッドを同時接続できるようにする
#define CFG_TUH_HUB               1
#define CFG_TUH_DEVICE_MAX        4
#define CFG_TUH_HID               8
#define CFG_TUH_HID_EPIN_BUFSIZE  64
#define CFG_TUH_HID_EPOUT_BUFSIZE 64

#define CFG_TUH_CDC               0
#define CFG_TUH_MSC               0
#define CFG_TUH_VENDOR            0

#endif
