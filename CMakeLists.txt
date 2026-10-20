cmake_minimum_required(VERSION 3.13)

# PICO_SDK_PATH 未設定なら手元の SDK を使う
if(NOT DEFINED ENV{PICO_SDK_PATH} AND NOT DEFINED PICO_SDK_PATH)
  set(PICO_SDK_PATH $ENV{HOME}/dev/pico-sdk)
endif()

include(pico_sdk_import.cmake)

# 接続先: MSX または MD (メガドライブ 3ボタン)
set(JOY_TARGET MSX CACHE STRING "Target machine (MSX or MD)")
set_property(CACHE JOY_TARGET PROPERTY STRINGS MSX MD)

# 出力回路: 0=74LVC07A, 1=NPN/MOSFET, 2=FXMA108
set(OUT_MODE 0 CACHE STRING "Output circuit (0=74LVC07A, 1=NPN, 2=FXMA108)")

if(JOY_TARGET STREQUAL "MD")
  set(APP usb2mdjoy)
  set(PORT_SRC src/md_port.c)
  set(TARGET_MD 1)
elseif(JOY_TARGET STREQUAL "MSX")
  set(APP usb2msxjoy)
  set(PORT_SRC src/msx_port.c)
  set(TARGET_MD 0)
else()
  message(FATAL_ERROR "JOY_TARGET must be MSX or MD")
endif()

project(${APP} C CXX ASM)
set(CMAKE_C_STANDARD 11)

pico_sdk_init()

add_executable(${APP}
  src/main.c
  src/config.c
  src/hid_gamepad.c
  ${PORT_SRC}
)

target_include_directories(${APP} PRIVATE src)
target_link_libraries(${APP} PRIVATE pico_stdlib pico_multicore tinyusb_host)
target_compile_definitions(${APP} PRIVATE OUT_MODE=${OUT_MODE} JOY_TARGET_MD=${TARGET_MD})

# ネイティブ USB はホストに使うので、デバッグ出力は UART0 (GP0=TX, GP1=RX, 115200bps)
pico_enable_stdio_usb(${APP} 0)
pico_enable_stdio_uart(${APP} 1)

pico_add_extra_outputs(${APP})
