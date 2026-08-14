VBCC := /Users/sah/6502/vbcc65816-mac
CC   := $(VBCC)/bin/vbcc65816
AS   := /Users/sah/6502/vasm-2.0f/vasm/vasm6502_oldstyle
LD   := /Users/sah/6502/vlink-src/vlink/vlink

CFLAGS  := -iigs -const-in-data -unsigned-char -mask-opt -O=0
AFLAGS  := -816 -Fvobj -vobj3 -quiet -nowarn=62 -opt-branch -ldots
LDFLAGS := -b rawbin -T link.ld -e _start

BUILD := build
OBJS  := $(BUILD)/startup.o $(BUILD)/main.o $(BUILD)/console.o

all: $(BUILD)/minixgs.po

$(BUILD)/%.s: kernel/%.c
	$(CC) $(CFLAGS) -Ikernel $< -o=$@

$(BUILD)/%.o: kernel/%.s
	$(AS) $(AFLAGS) $< -o $@

$(BUILD)/%.o: $(BUILD)/%.s
	$(AS) $(AFLAGS) $< -o $@

$(BUILD)/bootblock.bin: boot/bootblock.s
	$(AS) -816 -quiet -nowarn=62 -Fbin boot/bootblock.s -o $@

$(BUILD)/kernel.raw: $(OBJS)
	$(LD) $(LDFLAGS) $(OBJS) -o $@

$(BUILD)/minixgs.po: $(BUILD)/bootblock.bin $(BUILD)/kernel.raw
	python3 tools/mkdisk.py $^ $@

clean:
	rm -rf $(BUILD)/*.s $(BUILD)/*.o $(BUILD)/*.bin $(BUILD)/*.raw $(BUILD)/*.po

.PHONY: all clean
