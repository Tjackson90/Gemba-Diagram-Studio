"""Import lesson libraries without replacing a user's existing definitions."""
from copy import deepcopy
import data.custom_library as library


def import_library(project):
    incoming = project.get('custom_library')
    if incoming is None:
        return project
    library._validate_library(incoming)
    merged = library.load_raw()
    renamed = {'scales': {}, 'arpeggios': {}}
    changed = False
    for kind, entries in incoming.items():
        for name, intervals in entries.items():
            target = name
            counter = 2
            while target in merged[kind] and merged[kind][target] != intervals:
                target = f'{name} (import {counter})'
                counter += 1
            if target not in merged[kind]:
                merged[kind][target] = intervals
                changed = True
            renamed[kind][library.CUSTOM_PREFIX+name] = library.CUSTOM_PREFIX+target
    if changed:
        library._save_raw(merged)
    from data.scales import SCALE_INTERVALS, SCALE_NAMES
    from data.arpeggios import ARPEGGIO_INTERVALS, ARPEGGIO_NAMES
    library.load_into_scale_dicts(SCALE_INTERVALS, SCALE_NAMES)
    library.load_into_arpeggio_dicts(ARPEGGIO_INTERVALS, ARPEGGIO_NAMES)
    def rewrite(value, key=''):
        if isinstance(value, dict):
            result = {k:rewrite(v, k) for k,v in value.items()}
            if value.get('mode') == 'ArpProg' and isinstance(value.get('override'), str):
                result['override'] = renamed['arpeggios'].get(value['override'], value['override'])
            return result
        if isinstance(value, list):
            return [rewrite(v, key) for v in value]
        if isinstance(value, str):
            if key in ('scale', 'scale_name', 'scale_type_var'):
                return renamed['scales'].get(value, value)
            if key in ('arp', 'arp_type', 'arp_name', 'arp_type_var', '_arp_prog_type_var'):
                return renamed['arpeggios'].get(value, value)
        return value
    return rewrite(deepcopy(project))
