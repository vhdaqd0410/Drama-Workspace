// fetchEpisodeStatus 补丁
// === 扩展 fetchEpisodeStatus — 拿到数据后也更新展开面板 ===
const _origFetchEpisodeStatus = typeof fetchEpisodeStatus !== 'undefined' ? fetchEpisodeStatus : null;
