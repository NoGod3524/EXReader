"""Run the real dispatcher against a native echo stand-in, never an agent."""
import argparse, json, os, shutil, subprocess, tempfile
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('dispatch',type=Path)
p.add_argument('echo',type=Path)
p.add_argument('report',type=Path)
p.add_argument('--require-fixed',action='store_true')
a=p.parse_args()
results=[]
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    worktree=root/'work tree 中文';worktree.mkdir()
    for engine,rel in [('codex','OpenAI/Codex/bin/1/codex.exe'),('claude','Claude-Data/claude_pzs8sxrjxfjjc/claude-code/1/claude.exe')]:
        exe=root/rel;exe.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a.echo,exe)
        out=root/(engine+' output.json');meta=root/(engine+' metadata.json');record=root/(engine+' argv.json')
        prompt='中文 "quote" and slash\\\nsecond line'
        env=dict(os.environ,LOCALAPPDATA=str(root),EXR_ECHO_METADATA=str(meta),EXR_ECHO_ARGV=str(record),EXR_ECHO_EXIT='7',
                 DSH_AGENT_CORES='2',DSH_AGENT_PRIORITY='BelowNormal',DSH_AGENT_BUILD_JOBS='2')
        args=['pwsh','-NoProfile','-File',str(a.dispatch.resolve()),'-Engine',engine,'-Worktree',str(worktree),'-Prompt',prompt,'-Out',str(out)]
        proc=subprocess.run(args,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
        metadata=json.loads(meta.read_text()) if meta.exists() else None
        content=out.read_text(encoding='utf-8-sig') if out.exists() else None
        argv=json.loads(record.read_text()) if record.exists() else None
        for line in ([content] if content else [])+proc.stdout.splitlines():
            try:
                candidate=json.loads(line)
                if isinstance(candidate,list):argv=candidate;break
            except (ValueError,TypeError):pass
        results.append(dict(engine=engine,exit=proc.returncode,argv=argv,prompt_matches=bool(argv and argv[-1]==prompt),
             metadata=metadata,out=content,stdout=proc.stdout,stderr=proc.stderr,
             priority_ok=bool(metadata and metadata['priority']==0x4000),
             affinity_ok=bool(metadata and metadata['affinity'].bit_count()==2),
             hidden_ok=bool(metadata and metadata['startup_flags']&1 and metadata['show_window']==0)))
a.report.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps([{k:v for k,v in r.items() if k not in ['argv','stdout','stderr','out']} for r in results]))
if a.require_fixed:
    assert all(r['exit']==7 and r['prompt_matches'] and r['priority_ok'] and r['affinity_ok'] and r['hidden_ok'] for r in results)
    assert results[1]['out'] and json.loads(results[1]['out'])==results[1]['argv']
    assert all('echo stderr sentinel' in r['stderr'] for r in results)
    assert any(json.loads(line)==results[0]['argv'] for line in results[0]['stdout'].splitlines() if line.startswith('['))
    codex=results[0]['argv']
    import tomllib
    overrides=[tomllib.loads(codex[i+1]) for i,v in enumerate(codex[:-1]) if v=='-c']
    for plugin in ['computer-use@openai-bundled','unified-computer-use@openai-bundled','browser@openai-bundled']:
        assert any(o.get('plugins',{}).get(plugin,{}).get('enabled') is False for o in overrides)
    for key in ['BROWSER_USE_TINYSKY_ENABLED','SKY_CUA_NATIVE_PIPE']:
        assert any(o.get('mcp_servers',{}).get('node_repl',{}).get('env',{}).get(key)=='0' for o in overrides)
    claude=results[1]['argv']
    assert '--no-chrome' in claude and '--disallowedTools' in claude and 'mcp__windows-mcp__*' in claude
