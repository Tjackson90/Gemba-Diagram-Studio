"""Versioned, portable lesson documents and declarative render specifications."""
from dataclasses import dataclass, field
from copy import deepcopy
from functools import wraps
import inspect
import json
import config

RENDERERS = {}


def record_render(function):
    """Record rendering inputs, rather than making an export enlarge preview pixels."""
    RENDERERS[function.__name__] = function
    signature = inspect.signature(function)
    @wraps(function)
    def render(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        if 'width' in bound.arguments:
            config.validate_size(bound.arguments['width'], bound.arguments['height'])
        image = function(*args, **kwargs)
        params = deepcopy(dict(bound.arguments))
        for name in ('highlighted_notes', 'highlighted_strings'):
            params.pop(name, None)
        image.info['render_spec'] = {'renderer': function.__name__, 'params': params,
                                     'size': list(image.size)}
        from data.instrument import settings
        image.info['render_spec']['instrument'] = settings()
        from diagrams.style import name
        image.info['render_spec']['theme'] = name()
        return image
    return render


def render_spec(spec, target=None, **overrides):
    # Importing populates the explicit allowlist; files never name arbitrary callables.
    from diagrams import chord_diagram, scale_diagram, progression_diagram, scale_progression_diagram, tab_diagram
    name = spec['renderer']
    if name not in RENDERERS:
        raise ValueError(f'Unknown renderer: {name}')
    params = deepcopy(spec['params'])
    params.update(overrides)
    if params.get('bg_color') is not None:
        params['bg_color'] = tuple(params['bg_color'])
    if target:
        config.validate_size(*target)
        source_w, source_h = spec['size']
        factor = min(target[0]/source_w, target[1]/source_h)
        for key in ('width', 'height', 'panel_w', 'panel_h', 'chord_w', 'chord_h', 'padding', 'title_height', 'label_height', 'roman_height'):
            if key in params:
                params[key] = max(1, round(params[key]*factor))
    from data.instrument import instrument
    from diagrams.style import theme
    with instrument(spec.get('instrument', {'tuning':'Standard','capo':0,'left_handed':False})), theme(spec.get('theme','Volt')):
        return RENDERERS[name](**params)


@dataclass
class CurrentDocument:
    name: str = ''
    frets: list | None = None
    fingers: list | None = None
    root_semitone: int | None = None
    scale_notes: list | None = None
    is_arpeggio: bool = False
    progression: list | None = None
    prog_title: str = ''
    scale_prog_items: list | None = None
    arp_prog_items: list | None = None


@dataclass(frozen=True)
class ExportJob:
    """JSON provides an immutable boundary between widgets and worker execution."""
    payload: str

    @classmethod
    def capture(cls, value):
        return cls(json.dumps(value, ensure_ascii=False, allow_nan=False))

    def unpack(self):
        return json.loads(self.payload)


def validate_project(value):
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError('Unsupported lesson project version')
    if not isinstance(value.get('snapshot'), dict) or not isinstance(value.get('queue'), list):
        raise ValueError('Invalid lesson project')
    validate_snapshots([value['snapshot']])
    if 'custom_library' in value:
        from data.custom_library import _validate_library
        _validate_library(value['custom_library'])


def validate_snapshots(value):
    if not isinstance(value, list) or any(not isinstance(s, dict) or 'mode' not in s for s in value):
        raise ValueError('Expected a list of saved diagram snapshots')
    modes = {'Chord','Scale','Arpeggio','Progression','ScaleProg','ArpProg','Triads','ChordID','ChordLookup','Custom'}
    for snapshot in value:
        if snapshot['mode'] not in modes:
            raise ValueError('Unknown diagram mode in saved snapshot')
        if 'variables' in snapshot and (not isinstance(snapshot['variables'],dict) or
                any(type(v) not in (str,int,float,bool) for v in snapshot['variables'].values())):
            raise ValueError('Invalid saved settings')
