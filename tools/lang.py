"""Interface language of the GUI: English (the source strings in gui.py and theme.py) or Chinese.

tr(s) returns the Chinese text of an English string while the language is "zh", otherwise s itself; a string
without an entry stays English instead of failing.  The choice lives in gui.ini next to the program:

    [gui]
    language = zh

English when the file is missing, unreadable or names an unknown language.
"""
from __future__ import annotations

import configparser
from pathlib import Path

INI = "gui.ini"
LANGUAGES = (("en", "English"), ("zh", "中文"))      # code, name shown in the window (each in its own language)
current = "en"


def tr(s: str) -> str:
    return ZH.get(s, s) if current == "zh" else s


def name(code: str) -> str:
    return dict(LANGUAGES).get(code, LANGUAGES[0][1])


def code(name: str) -> str | None:
    return next((c for c, n in LANGUAGES if n == name), None)


def _read(path: Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser()
    try:
        cp.read(path, encoding="utf-8")
    except (OSError, configparser.Error, UnicodeDecodeError):
        pass
    return cp


def load(path: Path) -> str:
    """Set `current` from the ini file (English when it is missing or has no valid entry) and return it."""
    global current
    value = _read(path).get("gui", "language", fallback="en").strip().lower()
    current = value if value in dict(LANGUAGES) else "en"
    return current


def save(path: Path, code: str) -> None:
    """Write the language into the ini file, keeping its other entries.  OSError when it cannot be written."""
    cp = _read(path)
    if not cp.has_section("gui"):
        cp.add_section("gui")
    cp.set("gui", "language", code)
    with open(path, "w", encoding="utf-8") as f:
        cp.write(f)


ZH = {
    # window
    "regulation.bin randomizer · goods / spells / weapons": "regulation.bin 随机器 · 道具 / 法术 / 武器",
    "Language": "语言",
    "Ready": "就绪",
    "Browse…": "浏览…",
    "All files": "所有文件",
    # files
    "Files": "文件",
    "Input regulation.bin": "输入 regulation.bin",
    "Output file": "输出文件",
    "Open output folder": "打开输出目录",
    "{}: in the game's Game\\ folder or ModEngine2's mod folder; without it the output is zstd and larger": "{} 在游戏目录 Game\\ 里（ModEngine2 的 mod 文件夹里也有）；没有它只能输出 zstd 格式，文件更大",
    "Seed": "随机种子",
    "(blank = random; the log shows it, enter it here to reproduce a run)":
        "（留空 = 随机抽一个，运行后显示在日志里，填回去可复现）",
    "Compression": "压缩格式",
    # goods and spells
    "Goods and spells (effects are always randomized)": "道具与法术（效果总是随机）",
    "Effect assignment": "效果分配",
    "shuffle: each effect is used exactly once": "shuffle：每个效果恰好用一次",
    "random: effects may repeat": "random：效果可重复",
    "Use animation": "使用动作",
    "follows the effect": "跟着效果走",
    "from another item of the same kind (--split-anim same)": "同类道具里另选 (--split-anim same)",
    "from any item (--split-anim any)": "任意道具 (--split-anim any)",
    "Flask effects too (--include-flasks)": "圣杯瓶效果也随机 (--include-flasks)",
    "Random flask locations (--random-flask-locations)": "圣杯瓶获得位置随机 (--random-flask-locations)",
    "(both flasks are found elsewhere: a pickup, boss, NPC or shop; the first grace gives what was there)":
        "（两个圣杯瓶改到别处获得：拾取物、boss、NPC 或商店；第一个赐福改给那里原来的东西）",
    "Remembrances too (--include-remembrances)": "追忆也随机 (--include-remembrances)",
    "Sorcery / incantation effects (off = --no-spells)": "魔法 / 祷告效果随机（取消 = --no-spells）",
    "Shop prices (--random-prices)": "商店价格随机 (--random-prices)",
    "shuffle: permute the existing prices": "shuffle：打乱现有价格",
    "range: redraw within a range": "range：区间内重抽",
    "min": "最低",
    "max": "最高",
    "Sell prices of goods too (off = --no-sell-prices)": "道具售价也随机（取消 = --no-sell-prices）",
    "sell min": "售价最低",
    "sell max": "售价最高",
    "Sell prices of weapons / armor / Ashes of War too (--sell-equipment)":
        "武器 / 防具 / 战灰的售价也随机 (--sell-equipment)",
    # weapons
    "Weapons (all four = --weapons)": "武器（四项全选 = --weapons）",
    # item locations
    "Item locations": "道具获取位置",
    "Fun": "娱乐（fun）",
    "Random dialogue subtitles (--random-dialogue)": "对话字幕随机 (--random-dialogue)",
    "(every NPC line shows the subtitle of another line; the voices stay, so the NPC still speaks its own line)":
        "（每句 NPC 台词显示另一句的字幕；语音不动，NPC 念的还是自己原来那句）",
    "Joke shifu (--dialogue-jokes)": "笑话大师（joke shifu）(--dialogue-jokes)",
    "(the cut lines show a joke and join the shuffle; text archives: empty = the English and "
    "Chinese msg\\<language>\\menu_dlc02.msgbnd.dcx shipped with the program; or pick the game's "
    "own, one per language)":
        "（被砍的台词改成冷笑话并加入随机；文本档留空 = 用程序自带的英文、中文 msg\\<语言>\\menu_dlc02.msgbnd.dcx；"
        "也可以自己选游戏里的，每种语言一个）",
    "Somber weapons: affinities + Ashes of War (--somber-infusable)":
        "失色 / 独特武器可质变、可装战灰 (--somber-infusable)",
    "Random default skill and affinity on new weapons (--random-default-ash)":
        "默认战技随机，掉落 / 商店 / 初始武器的质变随机 (--random-default-ash)",
    "Random movesets (--random-movesets)": "动作模组随机 (--random-movesets)",
    "Mode": "模式",
    "Shields": "盾",
    "Bows": "弓",
    "bound variety": "bound 模式的 variety",
    "Standard rows keep their moveset (--keep-standard-moveset)": "Standard 行保留原动作 (--keep-standard-moveset)",
    "wepType follows (--weptype-follows, save validation untested)":
        "wepType 跟随动作 (--weptype-follows，未测试存档校验)",
    "Random stats (--random-stats)": "数值随机 (--random-stats)",
    "Groups": "分组",
    "Stamina cost multiplier range (--stamina-rate)": "出招耐力倍率范围 (--stamina-rate)",
    "to": "到",
    # buttons, command line, status
    "Preset": "常用设定",
    "Reset options": "恢复默认选项",
    "Randomize": "开始随机",
    "Preview (no file written)": "预览（不写文件）",
    "Repack only (no randomization)": "只重新压缩（不随机）",
    "Command line": "等价命令",
    "Bad option: {}": "参数有误：{}",
    "Running…": "运行中…",
    "Preview finished, no file written": "预览完成，没有写文件",
    "Done: {}": "完成：{}",
    "Failed, see the log": "失败，见日志",
    "Language not saved ({}): {}": "语言设置没能保存（{}）：{}",
    # checks and dialogs
    "{} must be an integer: {}": "{} 应为整数：{}",
    "min price": "最低价格",
    "max price": "最高价格",
    "min sell price": "最低售价",
    "max sell price": "最高售价",
    "Random stats needs at least one group": "数值随机至少要选一个分组",
    "The stamina multiplier range must satisfy 0 < min <= max, e.g. 0.3 to 1.7":
        "出招耐力倍率范围应满足 0 < 最低 <= 最高，例如 0.3 到 1.7",
    "The folder does not exist yet: {}": "目录还不存在：{}",
    "Input file not found: {}": "找不到输入文件：{}",
    "The output file must not be in the same folder as the input ({}): the reports and the joke shifu's msg folder "
    "are written next to the output and would end up in that folder, and an output named regulation.bin would "
    "replace the input. Create a new folder for the output; that also keeps the mods easy to manage.":
        "输出文件不能和输入文件放在同一目录（{}）：随机结果清单和笑话大师的 msg 目录会写在输出文件旁边，落进那个目录，"
        "而且同名的 regulation.bin 会把输入覆盖掉。建议创建新目录以方便 mod 管理。",
    "DLL not found: {}": "找不到 DLL：{}",
    "No {} given and there is none in the current folder ({}).\n\n"
    "It is in the game's Game\\ folder; pick it with Browse… to write the game's own KRAK format.\n\n"
    "Continue with the zstd format instead? The file will be about 35% larger and may exceed the game's size limit.":
        "没有指定 {}，当前目录（{}）里也没有。\n\n"
        "它在游戏目录 Game\\ 里，用“浏览…”选中它就能输出原版的 KRAK 格式。\n\n"
        "改用 zstd 格式继续吗？文件会大 35% 左右，可能超过游戏的大小上限。",
    "Written: {}\n\nReplace the regulation.bin in the mod folder with it to use it.\n"
    "mapping.txt / weapons.txt / spells.txt / dialogue.txt (what was randomized) are in the same folder; with jokes, "
    "copy its msg folder into the mod folder too.":
        "已写入 {}\n\n要覆盖 mod 目录里的 regulation.bin 才会生效。\n"
        "mapping.txt / weapons.txt / spells.txt / dialogue.txt（随机结果清单）在同一目录；加了冷笑话的话，旁边的 msg 目录也要一起复制进 mod 目录。",
    "Written: {}\n\nContent unchanged, only re-compressed. Replace the regulation.bin in the mod folder with it to use it.":
        "已写入 {}\n\n内容没有改动，只是重新压缩。要覆盖 mod 目录里的 regulation.bin 才会生效。",
    "The run failed, see the log": "运行失败，详见日志",
    "Still running. Quit anyway? The output file may be incomplete.": "还在运行中，确定退出？输出文件可能不完整。",
    # start-up failures
    "(this message was also written to {})": "（以上内容已写入 {}）",
    "This Python has no usable tkinter, the window cannot be shown.": "这个 Python 没有可用的 tkinter，无法显示窗口。",
    "Windows: install Python from python.org (tick \"tcl/tk and IDLE\" in the installer), delete "
    "%USERPROFILE%\\.venvs\\er_mod and run randomize_gui.bat / build_exe.bat again.":
        "Windows：安装 python.org 的 Python（安装时勾选 “tcl/tk and IDLE”），删除 %USERPROFILE%\\.venvs\\er_mod 后"
        "重新运行 randomize_gui.bat / build_exe.bat。",
    "The window failed to start:": "图形界面启动失败：",
}
