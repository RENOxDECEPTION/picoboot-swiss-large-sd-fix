# PicoBoot + large SD card not working in Swiss: the fix

If your PicoBoot GameCube boots Swiss but Swiss cannot open a large SD card in the SD2SP2, flash Swiss onto the PicoBoot chip itself. The card is then started only once, and it works.

This is a write-up of one troubleshooting session, with the evidence. It worked on the hardware listed below. It is not an official guide from the PicoBoot or Swiss projects.

## Is this your problem?

All of these were true here:

- PicoBoot modchip, SD2SP2 adapter, Swiss loaded from the SD card as `ipl.dol` (the standard setup).
- A large card (256GB SanDisk Ultra, FAT32, 64KB clusters). Smaller, older cards work fine in the same console.
- Swiss itself starts, so the card is readable at boot.
- Then one of:
  - Swiss hangs on **"Setting up device"**.
  - **SD Card via SD2SP2** is missing from the device list (only DVD, System, Memory Card).
  - Selecting it (press Z to show all devices) gives **"The physical drive does not work"**.

If Swiss never appears at all, this is a different problem.

## The fix

Swiss releases include a ready-made PicoBoot image. It puts Swiss in the chip's payload slot in place of gekkoboot, so nothing has to be loaded from the SD card before Swiss runs.

You need a USB cable on the Pico, which usually means opening the console.

1. Download the latest [Swiss release](https://github.com/emukidid/swiss-gc/releases) and extract it. The file you want is `PicoBoot/swiss_rXXXX.uf2`.
2. Download `picoboot_full_pico.uf2` from the [PicoBoot releases](https://github.com/webhdx/PicoBoot/releases) (`picoboot_full_pico2.uf2` for a Pico 2). Keep it: it is also how you undo this.
3. Hold **BOOTSEL** on the Pico while plugging in USB. A drive named `RPI-RP2` appears.
4. Copy `picoboot_full_pico.uf2` onto the drive. The Pico reboots and the drive disappears.
5. Enter BOOTSEL mode again and copy `swiss_rXXXX.uf2` onto the drive.
6. Unplug USB, insert the SD card, and power on from fully off.

Steps 4 and 5 can be one flash: `tools/merge_uf2.py` combines the two files into a single UF2.

```
python tools/merge_uf2.py picoboot_full_pico.uf2 swiss_r2174.uf2 combined.uf2
```

Why step 4 matters: the Swiss image only fills the payload slot (flash address `0x10080000`), which PicoBoot v0.4 and later read. On the first console here, flashing only the Swiss image onto the firmware that was already installed (version unknown) booted to the stock GameCube menu. Flashing PicoBoot v0.5.0 and the Swiss payload together fixed it.

### What goes on the SD card

Swiss no longer needs `ipl.dol`, but it still needs its patch file to boot games:

- `swiss/patches/apploader.img` from the same Swiss release (`Apploader/EXTRACT_TO_ROOT.zip`).
- Your games, for example in `games/`.

To make Swiss open the games folder on boot, set this in `swiss/settings/global.ini` (Swiss creates the file on first run), or press the autoload toggle while in that folder:

```
Autoload=sdc:/games
```

`sdc:` is the SD2SP2. Keep the file's CRLF line endings if you edit it by hand.

### Things to know

- **Updating Swiss** now means reflashing the Pico, not swapping a file on the card.
- **PicoBoot v0.5.0 warning:** its release notes say some consoles boot to the stock menu on v0.5.0 and recommend v0.3.1. v0.3.1 has no payload slot, so this fix is not available on it.
- **In-Game Reset:** with the "Reboot" mode, A + Z + Start landed on the stock GameCube menu, not Swiss. PicoBoot only injects its payload at a cold power-on. Swiss's other mode, "Apploader", loads Swiss from `swiss/patches/apploader.img` instead. It was not tested here, and it makes Swiss start the card a second time, which is the situation described below.
- **To undo:** flash `picoboot_full_pico.uf2` again and put Swiss back on the card as `ipl.dol`.

## What is actually going wrong

In the standard setup the card gets started twice:

1. gekkoboot (the small boot loader on the PicoBoot chip) starts the card from a cold power-on, reads `ipl.dol`, and shuts the card down. This always worked.
2. Swiss then starts the card again. This is where it fails.

Swiss and gekkoboot both use the SD driver from libogc2, and its shutdown path sends the card a reset (CMD0) before handing over. So Swiss always meets a card that has already been started and reset once, without a power cycle in between.

To see what the card does at that point, I built Swiss v0.7.0 with a patched libogc2 that prints every failed step of the SD startup on screen. The useful readings:

| Moment | Data line (card selected) | Meaning |
|---|---|---|
| Swiss's first contact, before sending anything | `ff` | Normal idle level |
| After Swiss's first command | `00` for 10 seconds | No valid answer, line held low |
| Every later attempt | `00` | Same |

The key detail is in the last test build: the first command Swiss sent was not a reset. It was CMD59 (CRC on/off), which is harmless. The card still answered with nothing but zeros. So after the handoff this card gives no valid response to any command until it is power-cycled.

I do not know why. The card is fine on a PC and fine when started from cold. Flashing Swiss to the chip avoids the second start entirely, which is why it works.

### What did not help

All of these were tried before the fix, on the same card:

- Reseating the card and the adapter.
- Lowering the SD speed to 13.5 MHz (`SD/IDE Speed=16MHz`).
- Older Swiss releases (r2119, r2041).
- A patched SD driver: startup at the slowest clock, up to 8 reset retries, a 5 second wait for the card to become ready.
- A patched SD driver that skips the reset, asks the card whether it is already running, and never resets it on shutdown.

### Reproducing the trace

`diagnostic/sdfix3.py` is the last version of the patch. It edits a libogc2 checkout and a Swiss checkout (tag `v0.7.0`) in place. Build both inside the `ghcr.io/extremscorner/libogc2` container: `make install` in libogc2, then `make` in Swiss. On a failed mount, Swiss shows a box starting with `SDFIX3` in place of the usual error.

Each line reads: `d` EXI device, `f` clock setting, the failing step, `r` last response bytes, `e` driver error flags, `t` milliseconds spent waiting for the card to leave idle, `c` reset attempts, `l` data line level (first read, after waiting, after reset), `p` answer to the CMD59 probe, `w` milliseconds waited after a reset.

Do not use this build to play games. It is a diagnostic: a failed startup takes about 3 minutes per attempt because of the long waits.

## Tested hardware

- GameCube with PicoBoot on an original Raspberry Pi Pico (RP2040), SD2SP2 adapter
- SanDisk Ultra 256GB microSDXC (SDSQUJQ-256G), FAT32, 64KB clusters, 128 games
- Swiss v0.7.0 (r2174), PicoBoot v0.5.0

One card on one console is a small sample. If this fixes your card, or does not, please open an issue with your card model and PicoBoot version.

## Credits

- [Swiss](https://github.com/emukidid/swiss-gc) by emukidid and Extrems, which ships the PicoBoot image this relies on.
- [PicoBoot](https://github.com/webhdx/PicoBoot) by webhdx.
- [gekkoboot](https://github.com/redolution/gekkoboot) and [libogc2](https://github.com/extremscorner/libogc2).

`diagnostic/sdfix3.py` contains small excerpts of libogc2 and Swiss source as patch context; those remain under their own licenses.
