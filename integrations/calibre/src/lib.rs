// SPDX-License-Identifier: GPL-3.0-only
use base64::Engine;
use std::{fs, path::PathBuf, process::{Command, Stdio}, time::{Duration, Instant}};

fn converter_path() -> Option<PathBuf> {
    let exe = if cfg!(windows) { "ebook-convert.exe" } else { "ebook-convert" };
    let mut candidates = Vec::new();
    if let Ok(current) = std::env::current_exe() {
        if let Some(parent) = current.parent() {
            candidates.extend([parent.join("calibre").join(exe), parent.join("Calibre Portable/Calibre").join(exe)]);
        }
    }
    for var in ["ProgramFiles", "ProgramFiles(x86)"] {
        if let Some(dir) = std::env::var_os(var) { candidates.push(PathBuf::from(dir).join("calibre2").join(exe)); }
    }
    candidates.push(PathBuf::from("/Applications/calibre.app/Contents/MacOS/ebook-convert"));
    if let Some(path) = std::env::var_os("PATH") { candidates.extend(std::env::split_paths(&path).map(|p| p.join(exe))); }
    candidates.into_iter().find(|path| path.is_file())
}

pub fn convert(input: Vec<u8>, from: String, to: String, title: String, author: String, cover: Option<String>) -> Result<Vec<u8>, String> {
    let allowed = ["pdf", "epub", "mobi", "azw3", "fb2", "txt", "rtf", "docx", "html"];
    if !allowed.contains(&from.as_str()) || !allowed.contains(&to.as_str()) { return Err("不支持的转换格式".into()); }
    if input.is_empty() || input.len() > 100 * 1024 * 1024 { return Err("转换文件须为 1 B 至 100 MB".into()); }
    let executable = converter_path().ok_or("未找到 calibre。请安装 calibre，或将 calibre 免安装文件放到 EXReader 旁的 calibre 文件夹。")?;
    let work = tempfile::tempdir().map_err(|e| e.to_string())?;
    let source = work.path().join(format!("input.{from}"));
    let target = work.path().join(format!("output.{to}"));
    fs::write(&source, input).map_err(|e| e.to_string())?;
    let log_path = work.path().join("convert.log");
    let log = fs::File::create(&log_path).map_err(|e| e.to_string())?;
    let mut command = Command::new(executable);
    command.arg(&source).arg(&target).arg("--title").arg(title).arg("--authors").arg(author)
        .stdin(Stdio::null()).stdout(Stdio::from(log.try_clone().map_err(|e| e.to_string())?)).stderr(Stdio::from(log));
    if let Some(data) = cover.filter(|s| !s.is_empty()) {
        let (prefix, encoded) = data.split_once(',').ok_or("封面格式无效")?;
        if !["data:image/jpeg;base64", "data:image/png;base64", "data:image/webp;base64", "data:image/gif;base64"].contains(&prefix) || encoded.len() > 8 * 1024 * 1024 { return Err("封面格式或大小无效".into()); }
        let bytes = base64::engine::general_purpose::STANDARD.decode(encoded).map_err(|_| "封面编码无效")?;
        let path = work.path().join(if prefix.contains("png") { "cover.png" } else if prefix.contains("webp") { "cover.webp" } else if prefix.contains("gif") { "cover.gif" } else { "cover.jpg" });
        fs::write(&path, bytes).map_err(|e| e.to_string())?;
        command.arg("--cover").arg(path);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command.spawn().map_err(|e| format!("无法启动 calibre：{e}"))?;
    let start = Instant::now();
    loop {
        match child.try_wait().map_err(|e| e.to_string())? {
            Some(status) => {
                if !status.success() {
                    let log = fs::read_to_string(&log_path).unwrap_or_default();
                    let excerpt: String = log.chars().rev().take(1600).collect::<String>().chars().rev().collect();
                    return Err(format!("calibre 转换失败：{excerpt}"));
                }
                break;
            }
            None if start.elapsed() > Duration::from_secs(180) => {
                let _ = child.kill(); let _ = child.wait();
                return Err("转换超过 3 分钟，已停止。请在 calibre 中处理这本书。".into());
            }
            None => std::thread::sleep(Duration::from_millis(100)),
        }
    }
    let size = fs::metadata(&target).map_err(|e| e.to_string())?.len();
    if size > 200 * 1024 * 1024 { return Err("输出超过 200 MB，请在 calibre 中直接转换".into()); }
    fs::read(target).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    #[test]
    fn rejects_unsafe_extensions_before_spawning() {
        assert!(super::convert(vec![1], "../../file".into(), "epub".into(), "".into(), "".into(), None).is_err());
        assert!(super::convert(vec![], "txt".into(), "epub".into(), "".into(), "".into(), None).is_err());
    }
}
