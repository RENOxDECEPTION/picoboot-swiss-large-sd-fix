#!/usr/bin/env python3
"""SDFIX3: trace + tolerant init for libogc2 sdgecko.c, and on-screen trace in Swiss.
Usage: sdfix.py <libogc2 dir> <swiss dir>. Every replacement asserts it matched."""
import re, sys

def sub(s, old, new, count=1):
    assert s.count(old) >= 1, f"missing: {old!r}"
    assert count == 0 or s.count(old) == count, f"{s.count(old)}x: {old!r}"
    return s.replace(old, new)

lib, swiss = sys.argv[1], sys.argv[2]

# ---------------- libogc2: libogc/sdgecko.c ----------------
p = f"{lib}/libogc/sdgecko.c"
s = open(p).read()

s = sub(s, "static u32 _ioTransferMode[MAX_DRIVE];", r'''static u32 _ioTransferMode[MAX_DRIVE];

/* SDFIX3 trace: one line per failed init step. [0] = since boot (never reset), [1] = current mount */
char sdgecko_trace[2][480];
u32 sdgecko_trace_inits;
static u32 _trLen[2],_trLast[2],_trRep[2],_trId,_trMs,_trCmd0;
static u8 _trLine[3],_trProbe;
static u32 _trWait,_sdReady[MAX_DRIVE];
static void __tr(s32 drv_no,const char *step)
{
	char line[96];
	int n,i;
	n = snprintf(line,sizeof(line),"d%u f%u %s r%02x%02x%02x%02x%02x e%04x t%u c%u l%02x%02x%02x p%02x w%u",
		(unsigned)_ioCardSelect[drv_no],(unsigned)_ioDefaultSpeed[drv_no],step,
		_ioResponse[drv_no][0],_ioResponse[drv_no][1],_ioResponse[drv_no][2],
		_ioResponse[drv_no][3],_ioResponse[drv_no][4],
		(unsigned)_ioError[drv_no],(unsigned)_trMs,(unsigned)_trCmd0,
		_trLine[0],_trLine[1],_trLine[2],_trProbe,(unsigned)_trWait);
	for(i=0;i<2;i++) {
		char *buf = sdgecko_trace[i];
		if(_trLen[i] && !strncmp(buf+_trLast[i],line,n) && (buf[_trLast[i]+n]=='\n' || buf[_trLast[i]+n]==' ')) {
			_trRep[i]++;	/* same as previous line: rewrite it with a repeat count */
			_trLen[i] = _trLast[i];
		} else {
			if(_trLen[i]+n+8>=sizeof(sdgecko_trace[i])) continue;	/* full: keep the earliest lines */
			_trRep[i] = 1;
			_trLast[i] = _trLen[i];
		}
		if(_trRep[i]>1) _trLen[i] += snprintf(buf+_trLen[i],sizeof(sdgecko_trace[i])-_trLen[i],"%s x%u\n",line,(unsigned)_trRep[i]);
		else _trLen[i] += snprintf(buf+_trLen[i],sizeof(sdgecko_trace[i])-_trLen[i],"%s\n",line);
	}
}
void sdgecko_trace_mark(void) { _trLen[1] = 0; _trRep[1] = 0; sdgecko_trace[1][0] = 0; }
u32 sdgecko_trace_id(void) { return _trId; }''')
s = sub(s, "#include <ogcsys.h>", "#include <ogcsys.h>\n#include <stdio.h>")

# ACMD41: allow up to 5 s (big SDXC cards can be slow to leave idle)
s = sub(s, "ret = __card_checktimeout(drv_no,startT,1500);", "ret = __card_checktimeout(drv_no,startT,5000);")

# CMD0: run the whole identification phase at the slowest EXI clock, retry reset up to 8x
s = sub(s, "static s32 __card_softreset(s32 drv_no)\n{", "static s32 __card_softreset1(s32 drv_no)\n{")
s = sub(s, "\t_ioCardFreq[drv_no] = _ioDefaultSpeed[drv_no];\n\n\tif(_ioFlag[drv_no]!=INITIALIZING) {",
           "\t_ioCardFreq[drv_no] = EXI_SPEED1MHZ;\n\n\tif(_ioFlag[drv_no]!=INITIALIZING) {")
s = sub(s, "\t\t\t\treturn __card_softreset(drv_no);", "\t\t\t\treturn __card_softreset1(drv_no);")
s = sub(s, "static bool __card_check(s32 drv_no)\n{", r'''/* read the data line with the card selected until it idles high (0xff) or ms elapse */
static u8 __card_linewait(s32 drv_no,u32 ms,u8 *first)
{
	u8 b = 0;
	u32 n = 0,t0 = gettick();

	EXI_LockEx(drv_no,_ioCardSelect[drv_no]);
	if(EXI_Select(drv_no,_ioCardSelect[drv_no],EXI_SPEED1MHZ)==0) { EXI_Unlock(drv_no); return 0xee; }
	do {
		if(EXI_ImmEx(drv_no,&b,1,EXI_READ)==0) { b = 0xed; break; }
		if(!n++ && first) *first = b;
	} while(b!=0xff && (gettick()-t0)/TB_TIMER_CLOCK<ms);
	EXI_Deselect(drv_no);
	EXI_Unlock(drv_no);
	return b;
}

/* after CMD0: clock with CS asserted until the card answers idle (0x01), goes quiet (0xff), or ms elapse */
static u8 __card_waitr1(s32 drv_no,u32 ms)
{
	u8 b = 0;
	u32 t0 = gettick();

	EXI_LockEx(drv_no,_ioCardSelect[drv_no]);
	if(EXI_Select(drv_no,_ioCardSelect[drv_no],EXI_SPEED1MHZ)==0) { EXI_Unlock(drv_no); return 0xee; }
	do {
		if(EXI_ImmEx(drv_no,&b,1,EXI_READ)==0) { b = 0xed; break; }
		_trWait = (gettick()-t0)/TB_TIMER_CLOCK;
	} while(b!=0x01 && b!=0xff && _trWait<ms);
	EXI_Deselect(drv_no);
	EXI_Unlock(drv_no);
	return b;
}

static s32 __card_softreset(s32 drv_no)
{
	s32 ret = CARDIO_ERROR_IOERROR;
	u32 i;

	_sdReady[drv_no] = 0;
	_trWait = 0;
	_ioFlag[drv_no] = INITIALIZING;
	_ioTransferMode[drv_no] = CARDIO_TRANSFER_IMM;	/* every read with CS asserted */
	_ioCardFreq[drv_no] = EXI_SPEED1MHZ;
	_trLine[1] = __card_linewait(drv_no,500,&_trLine[0]);
	_trLine[2] = _trLine[1];

	/* The boot loader already brought the card up in SPI mode. Ask it (CMD59 is harmless)
	   instead of resetting: this card stops answering after a second CMD0. */
	ret = __card_sendCMD59(drv_no,TRUE);
	_trProbe = _ioResponse[drv_no][0];
	if(ret==0 && _trProbe==0x01) return 0;	/* idle: carry on with CMD8/ACMD41 */
	if(ret==0 && _trProbe==0x00) {
		/* claims to be initialised already: believe it only if the OCR says powered up */
		if(__card_sendCMD58(drv_no)==0 && _ioResponse[drv_no][0]==0x00 && (_ioResponse[drv_no][1]&0x80)) {
			_ioFlag[drv_no] = INITIALIZED;	/* R1 is no longer expected to carry the idle bit */
			_sdReady[drv_no] = 1;
			return 0;
		}
	}

	/* no usable answer: one real reset at a time, then be patient */
	for(i=0;i<3;i++) {
		_ioFlag[drv_no] = INITIALIZING;
		if((ret=__card_writecmd0(drv_no))!=0) continue;
		_trLine[2] = __card_waitr1(drv_no,10000);
		ret = __card_sendCMD59(drv_no,TRUE);
		if(ret==0 && _ioResponse[drv_no][0]==0x01) break;
		ret = CARDIO_ERROR_IOERROR;
	}
	_trCmd0 = i;
	if(ret!=0) {	/* last resort: the stock sequence */
		_ioFlag[drv_no] = INITIALIZING;
		ret = __card_softreset1(drv_no);
	}
	return ret;
}

static bool __card_check(s32 drv_no)
{''')
# remember the EXI ID seen by the presence check
s = re.sub(r"(if\(EXI_GetID\(drv_no,[^;]*?&id\)==0\) return FALSE;)", r"\1 _trId = id;", s)
assert s.count("_trId = id;") == 3

# initIO: trace every bail-out
s = sub(s, "\t\tif(_ioFlag[drv_no]==INITIALIZED)\n\t\t\t__card_softreset(drv_no);\n", "")
a = s.index("s32 sdgecko_initIO(s32 drv_no)")
b = s.index("s32 sdgecko_preIO(s32 drv_no)")
f = s[a:b]
f = sub(f, "\t_ioCardInserted[drv_no] = __card_check(drv_no);",
        "\tif(_ioRetryCnt[drv_no]==0) { _trMs = 0; _trCmd0 = 0; sdgecko_trace_inits++; }\n"
        "\t_ioCardInserted[drv_no] = __card_check(drv_no);")
f = sub(f, "if(__card_softreset(drv_no)!=0) goto exit;", 'if(__card_softreset(drv_no)!=0) { __tr(drv_no,"CMD0"); goto exit; }\n\t\tif(_sdReady[drv_no]) { _initType[drv_no] = TYPE_SDHC; goto sdfix_ready; }')
f = sub(f, "\t\tif(_initType[drv_no]==TYPE_SDHC) {\n", "sdfix_ready:\n\t\t_ioFlag[drv_no] = INITIALIZING;\n\t\tif(_initType[drv_no]==TYPE_SDHC) {\n")
f = sub(f, "if(__card_sendCMD8(drv_no)!=0) goto exit;", 'if(__card_sendCMD8(drv_no)!=0) { __tr(drv_no,"CMD8"); goto exit; }')
f = sub(f, "if(!(_ioResponse[drv_no][0]&MMC_ERROR_IDLE)) goto exit;", 'if(!(_ioResponse[drv_no][0]&MMC_ERROR_IDLE)) { __tr(drv_no,"CMD8idle"); goto exit; }')
f = sub(f, "\t\t\telse goto exit;", '\t\t\telse { __tr(drv_no,"CMD8echo"); goto exit; }')
f = sub(f, "if(__card_sendopcond(drv_no)!=0) goto exit;",
        '{ u32 t0 = gettick(); s32 r = __card_sendopcond(drv_no); _trMs = (gettick()-t0)/TB_TIMER_CLOCK; if(r!=0) { __tr(drv_no,"ACMD41"); goto exit; } }')
f = sub(f, "if(__card_sendCMD59(drv_no,TRUE)!=0) goto exit;", 'if(__card_sendCMD59(drv_no,TRUE)!=0) { __tr(drv_no,"CMD59"); goto exit; }')
f = sub(f, "if(__card_sendCMD58(drv_no)!=0) goto exit;", 'if(__card_sendCMD58(drv_no)!=0) { __tr(drv_no,"CMD58"); goto exit; }')
f = sub(f, "if(__card_readcsd(drv_no)!=0) goto exit;", 'if(__card_readcsd(drv_no)!=0) { __tr(drv_no,"CSD"); goto exit; }', count=2)
# identification done: go to the working clock
f = sub(f, "if(__card_setblocklen(drv_no,_ioPageSize[drv_no])!=0) goto exit;",
        'if(__card_setblocklen(drv_no,_ioPageSize[drv_no])!=0) { __tr(drv_no,"CMD16"); goto exit; }\n'
        '\t\t_ioCardFreq[drv_no] = _ioDefaultSpeed[drv_no];')
f = sub(f, "if(__card_sendCMD6(drv_no,0x00fffff0)!=0) goto exit;", 'if(__card_sendCMD6(drv_no,0x00fffff0)!=0) { __tr(drv_no,"CMD6q"); goto exit; }')
f = sub(f, "if(__card_sendCMD6(drv_no,0x80fffff1)!=0) goto exit;", 'if(__card_sendCMD6(drv_no,0x80fffff1)!=0) { __tr(drv_no,"CMD6s"); goto exit; }')
f = sub(f, "if(__card_sd_status(drv_no)!=0) goto exit;", 'if(__card_sd_status(drv_no)!=0) { __tr(drv_no,"ACMD13"); goto exit; }')
f = sub(f, "\t\t_ioRetryCnt[drv_no] = 0;\n\t\t_ioFlag[drv_no] = INITIALIZED;",
        '\t\t__tr(drv_no,"OK");\n\t\t_ioRetryCnt[drv_no] = 0;\n\t\t_ioFlag[drv_no] = INITIALIZED;')
f = sub(f, "\t}\n\treturn CARDIO_ERROR_NOCARD;\n}", '\t}\n\t__tr(drv_no,"NOCARD");\n\treturn CARDIO_ERROR_NOCARD;\n}')
assert "goto exit;\n" not in re.sub(r"\{ __tr\(drv_no,\"\w+\"\); goto exit; \}", "", f), "untraced goto exit left"
s = s[:a] + f + s[b:]
open(p, "w").write(s)

# ---------------- Swiss: show the trace when a device fails to mount ----------------
p = f"{swiss}/cube/swiss/source/swiss.c"
s = open(p).read()
s = sub(s, "int needsDeviceChange = 0;",
        "int needsDeviceChange = 0;\nextern char sdgecko_trace[2][480];\nextern void sdgecko_trace_mark(void);\nextern u32 sdgecko_trace_inits;\nextern u32 sdgecko_trace_id(void);")
s = sub(s, "\t\t\t\tmsgBox = DrawRepublish(msgBox, DrawMessageBox(D_FAIL, statusMsg ? statusMsg : strerror(ret)));\n\t\t\t\tsleep(2);\n",
        '\t\t\t\tchar *sdfix = malloc(1400);\n'
        '\t\t\t\tsnprintf(sdfix, 1400, "SDFIX3 %s spd=%s inits=%u id=%08x\\nBOOT:\\n%sNOW:\\n%s(B) to close",\n'
        '\t\t\t\t\tstatusMsg ? statusMsg : strerror(ret), swissSettings.exiSpeed ? "27MHz":"13.5MHz",\n'
        '\t\t\t\t\t(unsigned)sdgecko_trace_inits, (unsigned)sdgecko_trace_id(), sdgecko_trace[0], sdgecko_trace[1]);\n'
        '\t\t\t\tmsgBox = DrawRepublish(msgBox, DrawTooltip(sdfix));\n'
        '\t\t\t\twhile(padsButtonsHeld() & BUTTON_B) { VIDEO_WaitVSync(); }\n'
        '\t\t\t\twhile(!(padsButtonsHeld() & BUTTON_B)) { VIDEO_WaitVSync(); }\n'
        '\t\t\t\tfree(sdfix);\n')
s = sub(s, "\t\t\ts32 ret = devices[DEVICE_CUR]->init( devices[DEVICE_CUR]->initial );\n\t\t\tif(ret) {\n\t\t\t\tneedsDeviceChange = 1;",
        "\t\t\tsdgecko_trace_mark();\n\t\t\ts32 ret = devices[DEVICE_CUR]->init( devices[DEVICE_CUR]->initial );\n\t\t\tif(ret) {\n\t\t\t\tneedsDeviceChange = 1;")
open(p, "w").write(s)
print("patched")
