"""Standalone atlas navigation around the shared spectrum cards."""
from collections import defaultdict
from .html import h
from ..io import digest


def atlas_body(body, sources, articles):
    groups = defaultdict(list)
    for source, article in zip(sources, articles):
        groups[source['object_id']].append((source, article))
    links, objects = [], []
    for name, epochs in groups.items():
        ident = 'object-' + digest(name)[:16]
        links.append(f'<li data-atlas-name="{h(name.lower())}"><a href="#{ident}">{h(name)}</a> ({len(epochs)})</li>')
        content = ''
        for source, article in epochs:
            label = str(source.get('observed_mjd') or source.get('mjd') or 'MJD unknown')
            content += f'<details class="atlas-epoch" open><summary>{h(label)} · {h(source["spectrum_id"])}</summary>{article}</details>'
        objects.append(f'<section id="{ident}" class="atlas-object"><h2>{h(name)}</h2>{content}</section>')
    start = body.index('<section id="spectra">')
    end = body.index('<section id="issues">', start)
    body = body[:start] + '<section id="spectra"><h2>Spectra &amp; matches</h2>' + ''.join(objects) + '</section>' + body[end:]
    sidebar = '<aside class="atlas-sidebar"><label for="atlas-search">Find object</label><input id="atlas-search" type="search"><nav aria-label="Objects"><ul>' + ''.join(links) + '</ul></nav></aside>'
    return '<div class="atlas-layout">' + sidebar + '<div class="atlas-content">' + body + '</div></div>'
