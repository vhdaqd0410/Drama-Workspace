/* fenji-core.js — 分集核心纯函数（手机端/桌面端共用，避免算法漂移）
 *
 * 挂载到 window.FenjiCore，提供：
 *   - splitEpisodes(total, persons)       : 把 [1..total] 均分给 persons，返回 {person: "start-end"}
 *   - rangeToAssign(rangeStr, person)     : 解析 "1-5,11-15" 等多段范围为 {集号: person}
 *   - rangeToNumbers(rangeStr)            : 解析范围字符串为集号数组 [1,2,3,...]
 *   - numbersToRanges(nums)               : 集号数组压缩为范围串 "1-3,7,9-12"
 *
 * 纯函数、无 DOM、无全局状态，两端直接 import/挂载使用。
 */
(function(){
  var FenjiCore = window.FenjiCore || (window.FenjiCore = {});

  // 把 [1..total] 平均分配给 persons，返回 { person: "start-end" }（每人一段，多的集数给前面的人）
  function splitEpisodes(total, persons){
    var out = {};
    if(!total || !persons || !persons.length) return out;
    var seg = total;
    var per = Math.floor(seg / persons.length);
    var rem = seg % persons.length;
    var cur = 1;
    persons.forEach(function(p, i){
      var sz = per + (i < rem ? 1 : 0);
      out[p] = cur + '-' + (cur + sz - 1);
      cur += sz;
    });
    return out;
  }

  // 解析范围串 "1-5,11-15" 为集号数组
  function rangeToNumbers(rangeStr){
    var nums = [];
    String(rangeStr||'').split(',').forEach(function(seg){
      seg = seg.trim();
      if(!seg) return;
      var parts = seg.split('-');
      var start = parseInt(parts[0]);
      var end = parseInt(parts[1] || parts[0]);
      if(isNaN(start)) return;
      if(isNaN(end)) end = start;
      for(var ep=start; ep<=end; ep++) nums.push(ep);
    });
    return nums;
  }

  // 解析范围串为 {集号: person}
  function rangeToAssign(rangeStr, person){
    var assign = {};
    rangeToNumbers(rangeStr).forEach(function(ep){ assign[ep] = person; });
    return assign;
  }

  // 集号数组压缩为范围串 "1-3,7,9-12"
  function numbersToRanges(nums){
    if(!nums || !nums.length) return '';
    var sorted = nums.slice().sort(function(a,b){ return a-b; });
    var parts = [];
    var start = sorted[0], prev = sorted[0];
    for(var i=1; i<sorted.length; i++){
      if(sorted[i] === prev+1){ prev = sorted[i]; }
      else {
        parts.push(start === prev ? String(start) : start + '-' + prev);
        start = prev = sorted[i];
      }
    }
    parts.push(start === prev ? String(start) : start + '-' + prev);
    return parts.join(',');
  }

  FenjiCore.splitEpisodes = splitEpisodes;
  FenjiCore.rangeToNumbers = rangeToNumbers;
  FenjiCore.rangeToAssign = rangeToAssign;
  FenjiCore.numbersToRanges = numbersToRanges;
  window.FenjiCore = FenjiCore;
})();
