"""Generate a self-contained, offline product showcase from computed sample data."""
import argparse
import html
import json
import os
import re
import sys
from pathlib import Path
import tempfile


def render(config):
    assets=Path(__file__).with_name('ui')
    raw=json.dumps(config,ensure_ascii=True).replace('<','\\u003c').replace('&','\\u0026')
    replacements={'TITLE':html.escape(config['name']+' — Workbench'),
                  'STYLE':assets.joinpath('style.css').read_text(encoding='utf-8'),
                  'DATA':raw,'SCRIPT':assets.joinpath('app.js').read_text(encoding='utf-8')}
    return re.sub(r'__(TITLE|STYLE|DATA|SCRIPT)__',lambda match:replacements[match.group(1)],
                  assets.joinpath('index.html').read_text(encoding='utf-8'))



def arguments(parser):
    parser.add_argument('-o','--output',type=Path,required=True)
    parser.add_argument('--overview',action='store_true',help='Generate the five-project overview; combine with --collection-links for a local collection')
    parser.add_argument('--force',action='store_true',help='Replace an existing regular output; existing user inputs/stores remain outside this workflow')
    parser.add_argument('--collection-links',action='store_true',help='Use sibling project-name.html links; generate all five project files beside index.html before using this option')


def generate(args):
    try:
        output=args.output
        if output.is_symlink() or (output.exists() and not output.is_file()):
            raise ValueError('showcase output must be a regular file, never a symlink')
        if output.exists() and not args.force:
            raise ValueError('showcase output exists; choose a new path or pass --force')
        if not output.parent.is_dir():
            raise ValueError('showcase output directory must already exist')
        config=({'catalog':True,'name':'Project collection','slug':'collection'} if args.overview else sample())
        config['local_collection']=args.collection_links
        document=render(config)
        descriptor,temporary=tempfile.mkstemp(prefix='.'+output.name+'.',suffix='.pending',dir=output.parent)
        try:
            with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
                stream.write(document);stream.flush();os.fsync(stream.fileno())
            if args.force:
                if output.is_symlink():raise ValueError('refusing symlink output')
                os.replace(temporary,output)
            else:os.link(temporary,output)
        finally:Path(temporary).unlink(missing_ok=True)
        print('Showcase saved: '+str(output))
        return 0
    except (ValueError,OSError) as exc:
        print('showcase: '+str(exc),file=sys.stderr)
        return 2


def main(argv=None):
    parser=argparse.ArgumentParser(description="Generate an offline showcase from fictional inputs and actual computed examples; existing user stores remain untouched.")
    arguments(parser)
    return generate(parser.parse_args(argv))

def sample():
    from .fixture import fixture_scenario
    from .runner import run_check
    from .engine import replay
    reports=[run_check(fixture_scenario(name),fixture=name,max_depth=8,max_states=50000) for name in ('retry-conflict','retry-fixed')]
    def state(report,label,title,description):
        rows=[]
        for key,node in report['versions'].items():
            passed=node['passed_explored_states']
            rows.append({'id':key,'title':{'base':'The original application','left':'A retry is added','right':'The worker changes','merged':'Both changes are merged'}[key],'subtitle':key.capitalize()+' version','status':'Pass within bound' if passed else 'Interaction found','tone':'good' if passed else 'bad','detail':'No invariant failure was found for this version in the explored scope.' if passed else 'The merged version repeats an effect after a delayed acknowledgment. Each branch passed separately in this bounded case. The recorded witness shows the interaction.'})
        candidate=report.get('candidate');count=len(candidate['events']) if candidate else 0
        return {'label':label,'title':title,'description':description,'visual':['A safe left branch','A safe right branch','Inspect the merge'],'metrics':[{'value':sum(n['passed_explored_states'] for n in report['versions'].values()),'label':'Versions passing'},{'value':count,'label':'Witness events'},{'value':report['bounds']['max_depth'] if 'max_depth' in report['bounds'] else 8,'label':'Event depth bound'}],'rows':rows,'output':report,'trace':replay(fixture_scenario('retry-conflict'),candidate['events'])['trace'] if candidate else []}
    return {'name':'Interlock','slug':'interlock','icon':'layers','color':'#855294','description':'Find the small event sequence where two individually safe changes fail together. Make the interaction inspectable.','sample_title':'Safe alone. Surprising together.','insight':'A delayed acknowledgment can turn a retry and a worker change into duplicate effects. A concrete witness explains the interaction.','steps':[{'title':'Declare four versions','description':'Compare the base, left branch, right branch, and proposed merge.'},{'title':'Explore a bounded schedule','description':'Search explicit event orderings under declared depth and state limits.'},{'title':'Replay the witness','description':'Inspect the state changes and compare them with bundled real handlers.'}],'features':[{'icon':'branch','title':'Separate branch safety','description':'Distinguish an interaction from a failure already present in the base or an individual branch.'},{'icon':'clock','title':'A concrete sequence','description':'Keep the short event witness, explore its prefixes, and replay exact transitions.'},{'icon':'shield','title':'Honest search boundaries','description':'Keep incomplete exploration, source identity, and handler agreement visible in the evidence.'}],'command':'python3 -m interlock showcase -o interlock.html','scope':'Both examples were computed with the bundled model and actual bundled retry handlers. State switching replays captured reports; it does not inspect your Git branches or execute imported code.','footer':'Passing a finite model or bundled fixture is not a general safety proof for arbitrary applications.','states':[state(reports[0],'The conflicting merge','Three versions pass. The merge repeats an effect.','A four-event witness exposes an interaction between retry and deduplication changes.',),state(reports[1],'A compatible change','The compatible control passes in the checked scope.','Preserving the duplicate guard avoids the interaction in this bundled control.',)]}
