"""Publish the reviewed decisions for the exact 30 retained GCC SARIF records."""
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from runtime_routes import ROOT, OUT, progress

REVISION = 'db9bab668ac725a75f3f92919edec3625879c7a8'
REVIEWED_SOURCE = 'd9ffdbf0'
# Each entry was reviewed against the complete SARIF path and both source revisions.
REVIEWS = {
    '020:0': '事件45跳过 i=0; i<count 初始化循环，事件47又以 first=0<count 进入段落。count 未改变，条件矛盾。每个 types[i] 在 bidi.c:486–492 写入后才传给 paragraph。',
    '020:1': '事件43、45跳过初始化及段落循环，事件51却进入 i=0<count 的 line_levels。count 未改变；types 的全量赋值和 bases 的逐段赋值均先于读取。',
    '020:2': '事件43跳过 i=0<count 的全量赋值，事件45、47又要求 count>0 并读取 types[i-1]。不存在该路径；循环对 [0,count) 每项赋值。',
    '021:0': 'span 调用 field 固定读取8字节。field 只有 FT_Load_Sfnt_Table 成功且 length==8 才返回 EXR_OK；越界、取消、预算、短读均返回非零。调用方检查 status 后才执行 be32，不存在成功但未写入 bytes 的路径。',
    '029:0': '事件40走 root_seen==0，svg_parse:445 因而返回 EXR_FORMAT；事件43又假设 status==0。common.c:5–13 的 exr_fail 原样返回非零代码。成功路径在435–437同时设置 doc->root 和 root_seen。',
    '030:0': '分配结果保存在 font->faces[i].bytes，所有权未丢失。成功由 *out 返回 font；任一失败转 bad→exr_font_free。refs 初始为1，析构遍历已设置的 count，释放各 face->bytes，包括部分构建项。诊断在赋值处终止，没有实际丢失所有权的语句。',
    '032:0': 'calloc 结果保存在 face->ot，是随字体存活的表缓存。tables 任一加载失败调用 exr_ot_free；成功由 exr_font_free 遍历 faces 调用 exr_ot_free，释放3张表和 ot 本身。诊断在成员赋值处即称泄漏，没有所有权丢失路径。',
    '037:0': 'exr_document_cfi_path_create 先清空输出，但只有 *out=b.data 后返回 EXR_OK；空根路径也通过 put(&b,"") 分配结尾零，失败返回 EXR_LIMIT。quoted 调用方检查 status；trace 将提前错误返回视作成功后才得到 NULL path。',
    '045:0': 'relations 对同一未变 XML 节点集使用完全相同的 Relationship 谓词计数和填充。存在任何可填充节点则 count>0，calloc 已成功；count==0 则第二遍不会进入赋值。trace 跳过192的分配却在197填充，条件矛盾。',
    '050:0': '直接 cursor_create 路径：初始 next=pos=size=0，循环要求 count<source->size。每次 txt_byte 消费一个字节；缓存耗尽时 next==count<source->size，不能走 trace 中两次 EOF 返回。读取失败返回非零且退出。不可变 source 契约见 include/exr/formats.h。',
    '050:1': 'scan_source→cursor_create 路径同样受 count<source->size 约束。trace 事件19、28假设尚需前缀字节时已 EOF，却继续增加 count；实际未到源末尾，短读为0返回 EXR_IO，不能留下未写前缀并成功继续。',
    '050:2': 'scan_source→cursor_next→txt_scalar：trace 事件54在UTF-16第二字节缺失时返回 EXR_ENCODING，却在57假设 s==EXR_OK。成功且 has==1 的 txt_scalar 已写 cp；has==0 的所有 cp 读取均由短路条件挡住。',
    '050:3': 'anchor_create_source→scan_source 的事件66为UTF-16缺字节错误，69却视为成功。exr_fail 保持 EXR_ENCODING；cursor_next 在读取 cp 之前检查 s!=EXR_OK 并转 fail。',
    '050:4': 'find_source→scan_source 的事件64为UTF-16缺字节错误，67却视为成功。错误码不可能变为0；成功的 UTF-16 和 exr_next UTF-8 分支都给 cp 赋值。',
    '050:5': 'anchor_resolve_source→scan_source 的事件82为UTF-16缺字节错误，85却视为成功。cursor_next 先检查返回码，EOF 的 has==0 又使 has&&cp 和 !has||cp 短路，无法读取未赋值 cp。',
    '050:6': 'trace 在 cursor_create 参数错误后假设成功，又在 cursor_next(NULL) 返回 EXR_ARGUMENT 后假设 s==0。common.c 保持错误码；scan_source 两处均检查返回值。真正成功的 create 必定写入非空 c。',
    '052:0': '事件27明确标为 realloc 成功且搬迁，事件28却选择 bytes==NULL；请求大小为 (resource_count+1)*sizeof，count<10000，非零且不溢出。成功指针保存为 d->resource_data；失败保留旧指针供 document 析构。路径自相矛盾。',
    '052:1': 'resource 在返回 EXR_OK 以前必定执行 *index=d->resource_count++（旧223，当前227）；此前失败返回 EXR_LIMIT/EXR_MEMORY，此后失败也返回非零。exr_kf8 在 status!=EXR_OK 时跳走，只有已赋值 index 才传入 exr_xhtml_positions。',
    '056:0': '直接 txt_find_paragraph：point 是最后一个 paragraph<=目标的检查点；points[0].paragraph=0。重放起点 i 因而<=目标，525循环至少执行一次并由 cursor_next 写 offset。trace 假设 i>paragraph 与私有检查点不变量矛盾。',
    '056:1': 'txt_prepare→txt_find_paragraph：仍选择<=目标的检查点；其他分支起点为目标本身或已知更小的 cursor_paragraph+1。循环不可能被跳过，status 和 line 验证后才读取 offset。',
    '056:2': 'txt_node_span→txt_find_paragraph：base+i 是合法段落编号；检查点选择保证重放起点<=base+i。trace 在523取检查点后假设525循环零次，违反503的选择条件及首检查点为0的不变量。',
    '056:3': 'txt_text 二分定位→txt_find_paragraph：每次目标都在 v->count 内；检查点序列递增且首项为0，所以至少调用一次 cursor_next。构造时671写入段落号，压缩666只保留偶数项，不破坏顺序或首项。',
    '056:4': 'txt_node→txt_node_span→txt_find_paragraph：首项0和升序检查点由私有构造器维护，503只选择<=目标的项。trace 的 i>paragraph 不可达；成功 cursor_next 在入口即初始化 offset。',
    '056:5': 'txt_text→txt_prepare 再入 txt_find_paragraph：缓存命中直接返回已保存值；非命中各分支保证 i<=目标。trace 最后恢复的检查点不能大于目标，故offset赋值循环必经。检查点结构不对调用方开放。',
    '065:0': 'exr_publication_load 检查参数、调用加载器，并专门将 status==OK且doc==NULL 改为 EXR_FORMAT。唯一成功返回先写 *out=doc；range_expand 只在 status==OK 时调用 content_unit。trace 跳过非零错误码语义。',
    '072:0': '先沿 first/next 计数 n，再遍历同一稳定的 Annots 链。n==0必有 first==EXR_PDF_NONE，不能进入第二遍。n>0才分配且检查 entries。trace 事件12假设n==0，14却假设first非NONE，互相矛盾。',
    '072:1': 'array 入口清零 values/count；空或缺失数组成功时 n=0，被 n!=4 拒绝。有4项则必须成功 malloc 并填充后才设置 out/count。任何失败返回非零。不存在 status==OK、n==4、values==NULL 的组合。',
    '101:0': 'chunk_offset 传入读取大小固定为4或8；exr_bmff_read 的 done 初始0，while(done<size)不能像事件11那样直接跳过。每次read_at须返回1..剩余字节数，成功只可能已完整填充 b。',
    '101:1': 'sample_size 的 width==16分支传入2字节；done=0不可能满足trace事件15的 done>=size。非零短读重试到完整长度，0或过长回调结果返回EXR_IO，调用方先检查status。',
    '101:2': 'sample_size 的 width==8分支传入1字节；trace事件15跳过 done=0<size=1 的循环不可达。成功至少写入 b[0]，读取失败无法越过status检查。',
}


def main():
    previous = ROOT / 'evidence/quality-20261108'
    rows = [r for r in json.loads((previous / 'diagnostics.json').read_text(encoding='utf-8'))['rows']
            if r['classification'] == 'project']
    assert len(rows) == 30 and set(REVIEWS) == {r['id'] for r in rows}
    units = json.loads(gzip.decompress((previous / 'analyzer-results.json.gz').read_bytes()))
    current = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    result = []
    for row in rows:
        old = subprocess.check_output(['git', 'show', REVISION+':'+row['file']], cwd=ROOT)
        new = (ROOT / row['file']).read_bytes()
        reviewed = subprocess.check_output(['git', 'show', REVIEWED_SOURCE+':'+row['file']], cwd=ROOT)
        assert new.decode().splitlines() == reviewed.decode().splitlines(), 'Source changed: re-review '+row['file']
        mapping = {}
        for tag, a, b, c, d in difflib.SequenceMatcher(None, old.decode().splitlines(), new.decode().splitlines(), autojunk=False).get_opcodes():
            if tag == 'equal': mapping.update({i+1:c+i-a+1 for i in range(a,b)})
        unit = next(u for u in units if u['id'] == int(row['id'].split(':')[0]))
        diagnostic = unit['diagnostics'][row['sarif_result_index']]
        trace = [f"{row['id']} {row['file']}:{row['line']} {row['message']}"]
        for flow in diagnostic.get('codeFlows', []):
            for thread in flow['threadFlows']:
                for event in thread['locations']:
                    loc = event['location']; physical = loc.get('physicalLocation', {})
                    file = Path(physical.get('artifactLocation', {}).get('uri', '?')).name
                    line = physical.get('region', {}).get('startLine', '?')
                    trace.append(f"{event.get('executionOrder', '?')} {file}:{line} {loc.get('message', {}).get('text', '')}")
        trace_name = row['id'].replace(':', '-')+'-trace.txt'
        (OUT / trace_name).write_text('\n'.join(trace)+'\n', encoding='utf-8')
        result.append(dict(id=row['id'], file=row['file'], original_line=row['line'],
                           current_line=mapping.get(row['line']), category=row['category'],
                           conclusion='confirmed_false_positive', conclusion_zh='确认是误报',
                           reason=REVIEWS[row['id']], source_proof=True, runtime_silence_is_not_proof=True,
                           original_sha256=hashlib.sha256(old).hexdigest(), current_sha256=hashlib.sha256(new).hexdigest(),
                           trace=trace_name, sarif=row['evidence'], sarif_result_index=row['sarif_result_index']))
    report = dict(original_revision=REVISION, reviewed_revision=current, total=30,
                  confirmed_defects=0, confirmed_false_positives=30, indeterminate=0, rows=result)
    (OUT / 'triage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines = ['# 30 条项目告警逐条核定', '',
             '核定完毕：**30/30 确认为误报；0 条确认缺陷；0 条无法判定。**', '',
             f'原分析源码 `{REVISION}`；本轮复核源码 `{current}`。原行号保持与 SARIF 对齐，同时记录当前行号和两版源码 SHA-256。', '',
             '以下结论来自返回码、循环不变量和所有权路径证明。ASan 不检查一般未初始化值，也不能代替泄漏检查；运行无诊断不作为误报依据。', '',
             '| # | SARIF ID | 原位置 → 当前行 | 结论 | 核定依据 |', '|---:|---|---|---|---|']
    for number, r in enumerate(result, 1):
        lines.append(f"| {number} | [{r['id']}]({r['trace']}) | `{r['file']}:{r['original_line']}` → {r['current_line']} | 确认是误报 | {r['reason']} |")
    (OUT / 'TRIAGE.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    progress('Step 3 complete: 30/30 analyzer records adjudicated; 30 confirmed false positives, 0 defects, 0 indeterminate; TRIAGE.md and triage.json retain per-path proofs.')


if __name__ == '__main__':
    main()
