#[cfg(not(any(target_os = "android", target_os = "ios")))]
mod converter;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default().setup(|app| {
        let window = tauri::WebviewWindowBuilder::new(app, "main", tauri::WebviewUrl::App("index.html".into()))
            .title("EXReader · 悦读")
            .inner_size(1180.0, 820.0)
            .min_inner_size(360.0, 500.0);
        #[cfg(target_os = "windows")]
        let window = {
            let exe_dir = std::env::current_exe()?.parent().unwrap().to_path_buf();
            if exe_dir.join(".portable").exists() {
                let data = exe_dir.join("EXReader-data");
                std::fs::create_dir_all(&data)?;
                window.data_directory(data)
            } else { window }
        };
        window.build()?;
        Ok(())
    });
    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    let builder = builder.invoke_handler(tauri::generate_handler![converter::convert_book]);
    builder.run(tauri::generate_context!()).expect("EXReader failed to start");
}
