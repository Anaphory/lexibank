from __future__ import unicode_literals, division
import sys
import transaction
import os
from _collections import defaultdict

from sqlalchemy import Index, func
from sqlalchemy.orm import joinedload_all
from clld.scripts.util import initializedb, Data
from clld.db.meta import DBSession
from clld.db.models import common
from clld.db.util import collkey, with_collkey_ddl
from clld_glottologfamily_plugin.util import load_families
from clldutils.path import Path
from clldutils.jsonlib import load
from pyglottolog.api import Glottolog
from pyconcepticon.api import Concepticon

import lexirumah
from lexirumah.scripts.util import import_cldf
from lexirumah.models import (
    LexiRumahLanguage, Concept, Provider, Counterpart, Cognateset, CognatesetCounterpart,
)


with_collkey_ddl()


def main(args):
    Index('ducet', collkey(common.Value.name)).create(DBSession.bind)
    repos = Path(os.path.expanduser('~')).joinpath('venvs/lexirumah/lexirumah-data')

    with transaction.manager:
        dataset = common.Dataset(
            id=lexirumah.__name__,
            name="lexirumah",
            publisher_name="Max Planck Institute for the Science of Human History",
            publisher_place="Jena",
            publisher_url="http://shh.mpg.de",
            license="http://creativecommons.org/licenses/by/4.0/",
            domain='lexirumah.model-ling.eu',
            contact='g.a.kaiping@hum.leidenuniv.nl',
            jsondata={
                'license_icon': 'cc-by.png',
                'license_name': 'Creative Commons Attribution 4.0 International License'})
        DBSession.add(dataset)

    glottolog_repos = Path(
        lexirumah.__file__).parent.parent.parent.parent.joinpath('glottolog3', 'glottolog')
    languoids = {l.id: l for l in Glottolog(glottolog_repos).languoids()}
    concepticon = Concepticon(
        Path(lexirumah.__file__).parent.parent.parent.parent.joinpath('concepticon', 'concepticon-data'))
    conceptsets = {c.id: c for c in concepticon.conceptsets.values()}

    skip = True
    for dname in sorted(repos.joinpath('datasets').iterdir(), key=lambda p: p.name):
        #if dname.name == 'benuecongo':
        #    skip = False
        #if skip:
        #    continue
        if dname.is_dir() and dname.name != '_template':
            mdpath = dname.joinpath('cldf', 'metadata.json')
            if mdpath.exists():
                print(dname.name)
                import_cldf(dname, load(mdpath), languoids, conceptsets)

    with transaction.manager:
        load_families(
            Data(),
            DBSession.query(LexiRumahLanguage),
            glottolog_repos=glottolog_repos,
            isolates_icon='tcccccc')


def prime_cache(args):
    """If data needs to be denormalized for lookup, do that here.
    This procedure should be separate from the db initialization, because
    it will have to be run periodically whenever data has been updated.
    """
    concept_labels = {r[0]: r[1] for r in
                      DBSession.query(common.Parameter.pk, common.Parameter.name)}
    for cogset in DBSession.query(Cognateset) \
            .options(joinedload_all(
                Cognateset.counterparts,
                #CognatesetCounterpart.counterpart,
                #common.Value.valueset
            )):
        concepts = set()
        for cp in cogset.counterparts:
            concepts.add(cp.counterpart.valueset.parameter_pk)
        cogset.name = "[{:}] (‘{:}’)".format(
            cogset.name,
            '’/‘'.join(sorted([concept_labels[pk] for pk in concepts])))
        cogset.representation = len(cogset.counterparts)
        source_cache = set()
        for rel in cogset.counterparts:
            for source in rel.sources:
                try:
                    links.add(link(self.dt.req, source, **self.get_attrs(source)))
                except AssertionError:
                    links.add(str(source))
        cogset.source_cache = '; '.join(source_cache)
        print(cogset, cogset.counterparts, [source for rel in cogset.source_cache for source in rel.sources])

    for concept in DBSession.query(Concept):
        concept.representation = DBSession.query(common.Language)\
            .join(common.ValueSet)\
            .filter(common.ValueSet.parameter_pk == concept.pk)\
            .distinct()\
            .count()

    for prov in DBSession.query(Provider):
        q = DBSession.query(common.ValueSet.language_pk)\
            .filter(common.ValueSet.contribution_pk == prov.pk)\
            .distinct()
        prov.language_count = q.count()
        prov.update_jsondata(language_pks=[r[0] for r in q])

        prov.parameter_count = DBSession.query(common.ValueSet.parameter_pk) \
            .filter(common.ValueSet.contribution_pk == prov.pk) \
            .distinct() \
            .count()
        prov.lexeme_count = DBSession.query(common.Value.pk)\
            .join(common.ValueSet)\
            .filter(common.ValueSet.contribution_pk == prov.pk)\
            .count()

        syns = defaultdict(dict)
        vs = common.ValueSet.__table__
        cp = Counterpart.__table__
        v = common.Value.__table__
        for vn, lpk, ppk, count in DBSession.query(
            cp.c.variety_name,
            vs.c.language_pk,
            vs.c.parameter_pk,
            func.count(v.c.pk)) \
            .filter(cp.c.pk == v.c.pk) \
            .filter(v.c.valueset_pk == vs.c.pk) \
            .filter(vs.c.contribution_pk == prov.pk) \
            .group_by(
            cp.c.variety_name,
            vs.c.language_pk,
            vs.c.parameter_pk
        ):
            syns[(vn, lpk)][ppk] = count

        if syns:
            prov.synonym_index = sum(
                [sum(list(counts.values())) / len(counts)
                 for counts in syns.values()]) / len(set(syns.keys()))


if __name__ == '__main__':
    initializedb(create=main, prime_cache=prime_cache)
    sys.exit(0)
