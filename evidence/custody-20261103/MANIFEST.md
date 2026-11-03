# 补丁保管快照 · 2026-11-03

四份 patch 原样复制自 `C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\projects\exreader-handoff\evidence-20261103\`。源 MANIFEST 记录生成时间为 2026-11-03 12:4x America/New_York，来源仓库副本为 `.tmp/exr-baseline`。

patch 本体已随本目录提交到仓库，custody 不再依赖 Actions。`ledger-evidence-custody.yml` 仍可按需生成另一份 artifact；其保留期不影响仓库中的副本。本次仅复制已有文件，未重新生成、修改或 apply 补丁。

## 来源 commit 与 SHA-256

| commit | patch 文件 | SHA-256 |
|---|---|---|
| `0be9b39384edd386b48b78d128515cf330611654` | `0001-Repair-F05-GTK-credential-readiness-bounded-cleanup-.patch` | `d5939df1dc646f7dc59952c5897a5c62eed1229563c7569ca0c84ec2c1ad04a4` |
| `c4d67540a0e17a86bd42ad9323cd269ce8959326` | `0001-Observe-original-GTK-import-dialogs-without-changing.patch` | `961bb872ec0d6e6d060c82d9c6c2b42d0c25dc8b98cb0c31d2350b4ce8fcfc3b` |
| `e2776a35c965f676f49c1cc85c709c24494b7743` | `0001-F03-ANDROID-F03-WINDOWS-Build-synchronization-profil.patch` | `be549d684044668e76ea75d67a3a02faea580179a09c4d4182f2db8609db290b` |
| `a375fd9baa70f040d5c144415c5ec0d2e541e5e6` | `0001-F03-SIX-HOST-Integrate-bounded-Apple-organization-re.patch` | `dd420b350ffae1bd756536bdf9f47eeff0fe83388b480a098e9bc961e8094b40` |

## 源文件生成命令

源 MANIFEST 记录使用 `git format-patch -1 -o <dir> <sha>`，逐个从真实 commit 对象导出。对应命令如下，供追溯生成方式：

```bash
for sha in 0be9b393 c4d67540 e2776a35 a375fd9b; do
  git -C <repo> format-patch -1 -o <dir> "$sha"
done
```

## 复核命令

在仓库根目录核对补丁字节：

```bash
cd evidence/custody-20261103
sha256sum -c <<'EOF'
d5939df1dc646f7dc59952c5897a5c62eed1229563c7569ca0c84ec2c1ad04a4  0001-Repair-F05-GTK-credential-readiness-bounded-cleanup-.patch
961bb872ec0d6e6d060c82d9c6c2b42d0c25dc8b98cb0c31d2350b4ce8fcfc3b  0001-Observe-original-GTK-import-dialogs-without-changing.patch
be549d684044668e76ea75d67a3a02faea580179a09c4d4182f2db8609db290b  0001-F03-ANDROID-F03-WINDOWS-Build-synchronization-profil.patch
dd420b350ffae1bd756536bdf9f47eeff0fe83388b480a098e9bc961e8094b40  0001-F03-SIX-HOST-Integrate-bounded-Apple-organization-re.patch
EOF
```

在仓库根目录核对来源对象及提交涉及的文件：

```bash
for sha in 0be9b393 c4d67540 e2776a35 a375fd9b; do
  git cat-file -t "$sha"     # commit
  git show "$sha" --stat
done
# 在适当的目标基线只检查可应用性，不落地：
git apply --check evidence/custody-20261103/<patch文件名>
```

`git apply --check` 的结果取决于目标工作树基线。SHA-256 以本表所登记的原始字节为准。
