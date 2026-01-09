import re
import requests

URL = "https://github.com/HavenOverflow/Cr50/raw/refs/heads/main/chip/haven/hw_b1_regdefs.h"

# e.g: KEYMGR0 -> KEYMGR
def _canonical_component(names):
    non_indexed = [n for n in names if not re.search(r"\d+$", n)]
    if non_indexed:
        return non_indexed[0]
    return names[0]

def register_lookup(addr: int) -> str | None:
    text = requests.get(URL, timeout=10).text

    # looks for "#define GC_*_BASE_ADDR *" and "#define GC_[component_name]_OFFSET *"
    base_re = re.compile(r"#define\s+GC_([A-Z0-9]+)_BASE_ADDR\s+(0x[0-9A-Fa-f]+)")
    offset_re = re.compile(
        r"#define\s+GC_([A-Z0-9]+)_([A-Z0-9_]+)_OFFSET\s+(0x[0-9A-Fa-f]+)"
    )

    bases_by_addr = {}
    for comp, val in base_re.findall(text):
        base = int(val, 16)
        bases_by_addr.setdefault(base, []).append(comp)

    addr_base = (addr >> 16) << 16
    if addr_base not in bases_by_addr:
        return None

    # we do this because stuff like KEYMGR0 comes before KEYMGR
    # but all the register definitions are as GC_KEYMGR, not GC_KEYMGR0
    component = _canonical_component(bases_by_addr[addr_base])
    offset_val = addr - addr_base

    for comp, name, val in offset_re.findall(text):
        if comp != component:
            continue
        if int(val, 16) == offset_val:
            return f"GC_{component}_{name}"

    return None