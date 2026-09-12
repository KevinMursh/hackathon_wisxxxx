import { writeFileSync } from 'node:fs';

const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const seg = (kind, tag, html) => `<div class="seg ${kind}"><span class="src ${kind}">${esc(tag)}</span>${html}</div>`;

const committee = (away) => `<div class="seg tpl" style="font-size:12.5px;line-height:1.6;"><span class="src tpl">模板 · 審議規則 §28 II 委員名單</span>訴願審議委員會主任委員　蔡庭榕${away ? '（公出）' : ''}<br>委員　陳明燦${away ? '（代理）' : ''}　陳立夫　張文郁　蔡進良　黃源銘　劉宗德　王藹芸　劉定基　董鈺琪　林泳玲　唐美芝</div>`;

const cases = {
  Draft: { title: '4a 草稿 · 不受理', file: 'Draft.dc.html', label: '不受理（§77 ②）', caseNo: '1147101471', docNo: '新北府訴決字第 1142185543 號', date: '114 年 12 月 31 日', away: true,
    parties: '　　訴願人　　　林○如<br>　　原處分機關　新北市政府警察局蘆洲分局',
    intro: '上列訴願人因違反洗錢防制法事件，不服原處分機關民國 112 年 11 月 12 日書面告誡（案件編號：1124430434）所為之處分，提起訴願一案，本府依法決定如下：',
    main: ['訴願不受理。'], mainTag: '模板 · §77② → 主文',
    facts: null,
    reasons: [
      ['ai','模型 · 引 §14 I、III · §77②','一、按訴願之提起，應自行政處分達到或公告期滿之次日起 30 日內為之，且以原行政處分機關或受理訴願機關收受訴願書之日期為準。提起訴願逾法定期間者，原處分即歸確定。此觀訴願法第 14 條第 1 項、第 3 項、第 77 條第 2 款之規定甚明。'],
      ['ai','模型 · 引行政程序法 §72 I','二、次按「送達，於應受送達人之住居所、事務所或營業所為之。…」行政程序法第 72 條第 1 項定有明文。'],
      ['edit','承辦人修改 · 補「已教示救濟方法」','三、本件系爭告誡書於 112 年 11 月 12 日送達訴願人本人，經訴願人簽收在案，又系爭告誡書內亦已教示救濟方法、期間及受理機關，此有經訴願人簽收之系爭告誡書影本附卷可稽。核計其 30 日法定期間應自 112 年 11 月 13 日起算，因訴願人居住所位於本市，毋須扣除在途期間，應至 112 年 12 月 12 日屆滿。惟訴願人遲至 114 年 10 月 20 日始提起訴願，已逾法定不變期間，本件訴願為程序不合，自不應受理。'],
    ],
    concl: '四、綜上論結，本件訴願為程序不合，依訴願法第 77 條第 2 款規定，決定如主文。',
    notice: true, attachments: [],
    refs: [['訴願法 §14 I、III','理由一'],['訴願法 §77 ②','理由一、四、主文'],['行政程序法 §72 I','理由二 · 逐字'],['案號 1137121361','113 年同型 · 理由三句型']],
    fields: [['事實段','不受理得不記載（§89 I ③）','na'],['救濟教示','附（不受理案）','on'],['另為處分期限','不適用','na'],['附表','無','na'],['主文分部','單一','na']],
  },
  DraftReject: { title: '4b 草稿 · 駁回', file: 'DraftReject.dc.html', label: '駁回（§79 I）', caseNo: '1147101441', docNo: '新北府訴決字第 1142145444 號', date: '114 年 12 月 17 日', away: true,
    parties: '　　訴願人　　　林○儒<br>　　原處分機關　新北市政府警察局汐止分局',
    intro: '上列訴願人因違反洗錢防制法事件，不服原處分機關民國 114 年 9 月 7 日新北警汐刑字 1144250329 號書面告誡所為之處分，提起訴願一案，本府依法決定如下：',
    main: ['訴願駁回。'], mainTag: '模板 · §79 I → 主文',
    facts: ['緣內政部警政署刑事警察局查獲馬○企業有限公司及豐○生技有限公司大量收集他人向蝦○拍賣購物平臺申請之帳號，涉犯洗錢防制法第 21 條第 1 項罪嫌。原處分機關認訴願人將系爭帳號交付他人使用，違反同法第 22 條第 1 項規定，遂為書面告誡。訴願人不服，於 114 年 9 月 30 日提起本件訴願，並據原處分機關檢卷答辯到府。茲摘敘訴辯意旨於次：','一、訴願意旨略謂：訴願人係出租賣場帳號取得營利所得，並不知情該帳號遭用於不法，原處分未給予陳述意見之機會等語。','二、答辯意旨略謂：訴願人於警詢供述以每週營利所得百分之十為對價出租帳號，顯不符一般商業交易習慣，原處分依法裁處，並無違誤等語。'],
    reasons: [
      ['ai','模型 · 引洗錢防制法 §22 I、II','一、按洗錢防制法第 22 條第 1 項規定：「任何人不得將自己或他人向金融機構申請開立之帳戶、向提供虛擬資產服務之事業或人員申請之帳號、向提供第三方支付服務之事業或人員申請之帳號交付、提供予他人使用。但符合一般商業、金融交易習慣，或基於親友間信賴關係或其他正當理由者，不在此限。」'],
      ['ai','模型 · 認事','二、卷查本案訴願人於 113 年 2 月 7 日將系爭帳號以每週賣場營利所得百分之十為對價交付他人使用，此有訴願人警詢筆錄、帳號交易紀錄等影本附卷可稽。原處分機關據以裁處告誡，揆諸前揭規定，洵屬有據。'],
      ['ai','模型 · 駁斥訴願主張','三、至訴願人主張不知情且未給予陳述意見之機會等語。惟查：訴願人以對價出租帳號，顯非一般商業交易習慣；又行政程序法第 103 條第 5 款規定，處分係依訴願人陳述所為者得不給予陳述意見機會。訴願人所訴各節，不足採據，原處分應予維持。'],
    ],
    concl: '四、綜上論結，本件訴願為無理由，依訴願法第 79 條第 1 項規定，決定如主文。',
    notice: true, attachments: [],
    refs: [['洗錢防制法 §22 I、II','理由一'],['行政程序法 §103 ⑤','理由三'],['訴願法 §79 I','綜上論結'],['北高行 114 簡上 13','「交付使用」判準']],
    fields: [['事實段','必載（實體審查）','on'],['訴辯意旨','訴願意旨 + 答辯意旨','on'],['救濟教示','附（駁回案）','on'],['證據清單','警詢筆錄、交易紀錄','on'],['主文分部','單一','na']],
  },
  DraftRevoke: { title: '4c 草稿 · 撤銷', file: 'DraftRevoke.dc.html', label: '原處分撤銷（§81 I，不另處）', caseNo: '1143051259', docNo: '新北府訴決字第 1141934721 號', date: '114 年 12 月 17 日', away: false,
    parties: '　　訴願人　　　劉○鑫即劉○鑫建築師事務所<br>　　原處分機關　新北市政府工務局',
    intro: '上列訴願人因違反建築法事件，不服原處分機關民國 114 年 7 月 4 日新北工使字第 1141305688 號函併附同文號處分書所為之處分，提起訴願一案，本府依法決定如下：',
    main: ['原處分撤銷。'], mainTag: '模板 · §81 I → 主文（時效消滅，不另處）',
    facts: ['緣訴願人受託辦理本市○○區○○○路 291 號 2 樓建築物 111 年度公共安全簽證及申報作業，於 111 年 6 月 9 日申報並經備查。原處分機關 112 年 7 月 4 日複查認防火門不符，涉簽證不實，於 114 年 7 月 4 日依建築法第 91 條之 1 第 1 款裁處 6 萬元罰鍰。訴願人不服，於 114 年 8 月 1 日提起本件訴願，並據原處分機關檢卷答辯到府。茲摘敘訴辯意旨於次：','一、訴願意旨略謂：原處分距申報日已逾 3 年等語。','二、答辯意旨略謂：經專案小組認定簽證不實，依法裁處應屬允當等語。'],
    reasons: [
      ['ai','模型 · 引建築法 §77 III、IV · §91-1 ①','一、按建築法第 77 條第 3 項、第 4 項及第 91 條之 1 第 1 款規定，辦理檢查簽證內容不實者，處 6 萬元以上 30 萬元以下罰鍰。'],
      ['ai','模型 · 認事','二、卷查訴願人 111 年 6 月 9 日申報之簽證內容與 112 年 7 月 4 日複查結果不符，此有複查情形紀錄表、現場照片及檢查報告書影本附卷可稽，原處分機關依法裁處，固非無據。'],
      ['edit','承辦人修改 · 補立法理由','三、惟按行政罰法第 27 條第 1 項及第 2 項規定，裁處權因三年期間之經過而消滅，自違反義務之行為終了時起算。查本案違法行為於 111 年 6 月 9 日申報不實時成立，原處分機關遲至 114 年 7 月 4 日始作成處分，顯已逾 3 年裁處權時效，原處分於法有違，爰予撤銷。'],
    ],
    concl: '四、綜上論結，本件訴願為有理由，依訴願法第 81 條第 1 項規定，決定如主文。',
    notice: false, attachments: ['附表 1（摘錄）.PDF','附表 6（摘錄）.PDF'],
    refs: [['建築法 §77 III、IV · §91-1 ①','理由一'],['行政罰法 §27 I、II','理由三 · 撤銷依據'],['訴願法 §81 I','綜上論結'],['裁罰基準附表 1、6','相關圖表']],
    fields: [['事實段','必載','on'],['救濟教示','不附（訴願人勝訴）','na'],['另為處分期限','不適用（時效消滅）','na'],['附表','2 份 · 文末「相關圖表」','on'],['主文分部','單一','na']],
  },
  DraftRemand: { title: '4d 草稿 · 撤銷另處', file: 'DraftRemand.dc.html', label: '撤銷另處（§81 I、II）', caseNo: '1147031321', docNo: '新北府訴決字第 1142006823 號', date: '114 年 11 月 26 日', away: true,
    parties: '　　訴願人　　　莊○婷<br>　　原處分機關　新北市政府警察局中和分局',
    intro: '上列訴願人因違反洗錢防制法事件，不服原處分機關民國 114 年 7 月 26 日告誡處分書（發文字號：11407180140）所為之處分，提起訴願一案，本府依法決定如下：',
    main: ['原處分撤銷，由原處分機關於 2 個月內另為適法之處分。'], mainTag: '模板 · §81 I、II → 主文（程序瑕疵，指定期間）',
    facts: ['緣訴願人於 114 年 6 月 28 日將自己之永○商業銀行、中○信託商業銀行等 2 帳戶交付予他人（Line 暱稱：辰 N）使用，致被害人匯入 30 萬元，系爭 2 帳戶遭列為警示帳戶。原處分機關認訴願人違反洗錢防制法第 22 條第 1 項規定，依同條第 2 項為告誡處分。訴願人不服，提起本件訴願，並據原處分機關檢卷答辯到府。茲摘敘訴辯意旨於次：','一、訴願意旨略謂：告誡書未載事實，訴願人無從知悉受處分之原因等語。','二、答辯意旨略謂：訴願人於警訊供述透過 Line 傳送帳戶予暱稱辰 N 之人，提供帳戶之行為已甚明灼等語。'],
    reasons: [
      ['ai','模型 · 引行政程序法 §96 I ② · §114 I、II','一、按行政程序法第 96 條第 1 項第 2 款規定，書面行政處分應記載主旨、事實、理由及其法令依據；第 114 條第 2 項規定，理由之補正僅得於訴願程序終結前為之。'],
      ['ai','模型 · 引最高行 93 判 1624、95 裁 2935','二、查本件系爭告誡書其事實欄空白，未載明應記載事項，已違反行政程序法第 96 條第 1 項第 2 款規定；且「事實」非屬得依第 114 條補正之事項（最高行政法院 93 年度判字第 1624 號判決、95 年度裁字第 2935 號裁定參照），自屬有瑕疵之行政處分，實難予以維持，應予撤銷，並由原處分機關於 2 個月內另為適法之處分，以資妥適。'],
    ],
    concl: '三、綜上論結，本件訴願為有理由，依訴願法第 81 條第 1 項及第 2 項規定，決定如主文。',
    notice: false, attachments: [],
    refs: [['行政程序法 §96 I ②','理由一、二'],['行政程序法 §114 I、II','理由一、二'],['最高行 93 判 1624 · 95 裁 2935','理由二 · 不得補正'],['訴願法 §81 I、II','主文、綜上論結']],
    fields: [['事實段','必載','on'],['救濟教示','不附（訴願人勝訴）','na'],['另為處分期限','2 個月（§81 II 指定相當期間）','on'],['附表','無','na'],['主文分部','單一','na']],
  },
  DraftMixed: { title: '4e 草稿 · 混合', file: 'DraftMixed.dc.html', label: '部分不受理、部分駁回（§77 ⑧ + §79 I）', caseNo: '1143070734', docNo: '新北府訴決字第 1141214066 號', date: '114 年 8 月 27 日', away: false,
    parties: '　　訴願人　　　施○迅即芯○海養生館<br>　　原處分機關　新北市政府工務局',
    intro: '上列訴願人因違反建築法事件，不服原處分機關民國 114 年 4 月 25 日新北工使字第 1140751419 號函併附同文號行政處分書所為之處分，提起訴願一案，本府依法決定如下：',
    main: ['原處分關於新臺幣 12 萬元罰鍰部分，訴願駁回。','原處分關於限期改善部分，訴願不受理。'], mainTag: '模板 · 處分內容拆 2 部分 → 主文 2 行',
    facts: ['緣訴願人為本市○○區○○路 1 段 65 號 1 樓、2 樓建築物之使用人，經本府聯合稽查查得現場設有按摩床 8 床，認擅自變更使用類組為「按摩場所（B 類 1 組）」，違反建築法第 73 條第 2 項，前經 113 年 1 月 23 日裁處 6 萬元並限期改善。嗣複查仍未改善，原處分機關於 114 年 4 月 25 日再裁處 12 萬元罰鍰並限期改善。訴願人不服，提起本件訴願，並據原處分機關檢卷答辯到府。茲摘敘訴辯意旨於次：','一、訴願意旨略謂：…等語。','二、答辯意旨略謂：…等語。'],
    reasons: [
      ['ai','模型 · 分部一 · 實體審查','一、關於不服原處分裁處 12 萬元罰鍰部分：按建築法第 73 條第 2 項、第 91 條第 1 項第 1 款規定…卷查…此有勘查紀錄表及現場照片附卷可稽…原處分關於裁處 12 萬元罰鍰部分，於法並無違誤，應予維持。'],
      ['ai','模型 · 分部二 · 引 §77⑧ + 釋字 546','二、關於不服原處分限期改善部分：按對於非行政處分或其他依法不屬訴願救濟範圍內之事項提起訴願者，應為不受理之決定。次按司法院釋字第 546 號解釋意旨略以，為訴願決定時已屬無法補救者，其訴願為無實益。查限期改善之期限業已屆至，縱經撤銷亦無從回復，訴願人此部分之訴願應為不受理之決定。'],
    ],
    concl: '三、綜上論結，本件訴願為部分程序不合，部分無理由，依訴願法第 77 條第 8 款及第 79 條第 1 項規定，決定如主文。',
    notice: true, attachments: ['附表 1（摘錄）.PDF'],
    refs: [['建築法 §73 II · §91 I ①','理由一'],['訴願法 §77 ⑧','理由二、主文第 2 行'],['釋字 546','理由二 · 無實益'],['訴願法 §79 I','理由一、主文第 1 行']],
    fields: [['事實段','必載（含實體部分）','on'],['救濟教示','附（含駁回部分）','on'],['主文分部','2 部分，逐部分列主文','on'],['綜上論結','「部分程序不合，部分無理由」雙款次','on'],['附表','1 份','on']],
  },
};

const shell = (c, body, side) => `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@400;600&display=swap">
  <style>
    body { margin: 0; font-family: 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; color: #1c1b19; background: #f4f3f0; }
    a { color: #1f5f6b; } a:hover { color: #164751; }
    .step { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 6px; font-size: 14px; color: #6b6862; }
    .step.on { background: #e6efef; color: #1f5f6b; font-weight: 500; }
    .step.done { color: #1c1b19; }
    .num { width: 22px; height: 22px; border-radius: 11px; border: 1.5px solid currentColor; display: flex; align-items: center; justify-content: center; font-size: 12px; }
    .doc { font-family: 'Noto Serif TC', 'PingFang TC', serif; font-size: 12.5px; line-height: 1.8; color: #1c1b19; }
    .seg { position: relative; padding: 4px 10px 4px 12px; border-left: 3px solid transparent; border-radius: 0 4px 4px 0; }
    .seg.tpl { border-left-color: #cfcbc3; }
    .seg.ai { border-left-color: #1f5f6b; background: #f7fafa; }
    .seg.edit { border-left-color: #9a6700; background: #fdf8ec; }
    .src { position: absolute; right: 8px; top: 3px; font-family: 'Noto Sans TC', sans-serif; font-size: 10px; padding: 1px 6px; border-radius: 4px; }
    .src.tpl { background: #efece6; color: #6b6862; }
    .src.ai { background: #e6efef; color: #1f5f6b; }
    .src.edit { background: #fbf1d9; color: #9a6700; }
    .h { text-align: center; font-weight: 600; }
    .ref { display: flex; flex-direction: column; gap: 2px; padding: 9px 14px; border-bottom: 1px solid #efece6; font-size: 12.5px; }
    .ref .k { font-weight: 500; display: flex; justify-content: space-between; gap: 8px; }
    .ref .v { color: #6b6862; font-size: 11.5px; }
    .ok { font-size: 11px; color: #2e7d4f; white-space: nowrap; }
    .fr { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 8px 14px; border-bottom: 1px solid #efece6; font-size: 12.5px; }
    .fr .d { width: 10px; height: 10px; border-radius: 5px; flex-shrink: 0; }
    .on { background: #2e7d4f; } .na { background: #cfcbc3; }
  </style>
</helmet>
<div style="width: 1440px; height: 900px; display: flex; flex-direction: column; background: #f4f3f0; overflow: hidden;">
  <div style="height: 56px; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; background: #fff; border-bottom: 1px solid #e2dfd8;">
    <div style="display: flex; align-items: center; gap: 16px;">
      <div style="font-size: 16px; font-weight: 700; color: #1f5f6b;">訴願審理輔助工作台</div>
      <div style="font-size: 13px; color: #6b6862;">新北市政府法制局</div>
    </div>
    <div style="display: flex; align-items: center; gap: 20px; font-size: 13px; color: #6b6862;">
      <div>案號 <span style="color: #1c1b19; font-weight: 500;">${c.caseNo}</span></div>
      <div>承辦人 <span style="color: #1c1b19;">王○○</span></div>
    </div>
  </div>
  <div style="flex-grow: 1; display: flex; min-height: 0;">
    <div style="width: 200px; padding: 20px 12px; display: flex; flex-direction: column; gap: 4px; border-right: 1px solid #e2dfd8; background: #fbfaf8;">
      <div class="step done"><div class="num">1</div><div>收案擷取</div></div>
      <div class="step done"><div class="num">2</div><div>程序檢核</div></div>
      <div class="step done"><div class="num">3</div><div>法規與案例</div></div>
      <div class="step on"><div class="num">4</div><div>草稿審核</div></div>
      <div class="step"><div class="num">5</div><div>稽核匯出</div></div>
    </div>
    <div style="flex-grow: 1; display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 2fr); gap: 20px; padding: 20px 24px; min-height: 0;">
      ${body}
      ${side}
    </div>
  </div>
</div>
</x-dc>
</body>
</html>
`;

for (const c of Object.values(cases)) {
  const parts = [];
  parts.push(seg('tpl','模板 · 抬頭', `<div class="h" style="font-size:16px;">新北市政府訴願決定書</div><div style="text-align:right;font-size:12px;">案號：${c.caseNo} 號</div>`));
  parts.push(seg('tpl','模板 · 當事人欄（§89 I ①②）', `${c.parties}<br>${esc(c.intro)}`));
  parts.push(seg('tpl', c.mainTag, `<div class="h">主　　文</div>${c.main.map(esc).join('<br>')}`));
  if (c.facts) parts.push(seg('ai','模型 · 事實段（緣…茲摘敘訴辯意旨於次）', `<div class="h">事　　實</div>${c.facts.map(esc).join('<br>')}`));
  else parts.push(seg('tpl','模板 · 不受理得不記載事實（§89 I ③）', `<div class="h">理　　由</div>`));
  if (c.facts) parts.push(seg('tpl','模板', `<div class="h">理　　由</div>`));
  for (const [k,t,x] of c.reasons) parts.push(seg(k,t,esc(x)));
  parts.push(seg('tpl','模板 · 款次同主文', esc(c.concl)));
  parts.push(committee(c.away));
  if (c.notice) parts.push(seg('tpl','模板 · §90 教示（不受理／駁回附）', `<span style="font-size:12px;color:#6b6862;">如不服本決定，得於決定書送達之次日起 2 個月內向臺北高等行政法院（地址：臺北市士林區福國路 101 號）提起行政訴訟。</span>`));
  else parts.push(seg('tpl','模板 · §90 教示省略（訴願人勝訴）', `<span style="font-size:12px;color:#a19d95;">（不附救濟教示）</span>`));
  parts.push(seg('tpl','模板 · 決定日期／發文字號', `<span style="font-size:12px;">中華民國 ${c.date}　　${c.docNo}</span>`));
  if (c.attachments.length) parts.push(seg('tpl','模板 · 相關圖表', `<span style="font-size:12px;">${c.attachments.map(a=>'相關圖表：'+esc(a)).join('　')}</span>`));

  const body = `<div style="background: #fff; border: 1px solid #e2dfd8; border-radius: 8px; display: flex; flex-direction: column; overflow: hidden;">
        <div style="padding: 10px 16px; border-bottom: 1px solid #e2dfd8; display: flex; align-items: center; gap: 14px; font-size: 12px; color: #6b6862;">
          <div style="font-size: 14px; font-weight: 500; color: #1c1b19;">決定書草稿 · ${esc(c.label)}</div>
          <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 9px; height: 9px; background: #cfcbc3; border-radius: 2px;"></div>模板</div>
          <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 9px; height: 9px; background: #1f5f6b; border-radius: 2px;"></div>模型</div>
          <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 9px; height: 9px; background: #9a6700; border-radius: 2px;"></div>承辦人修改</div>
        </div>
        <div class="doc" style="padding: 12px 20px; display: flex; flex-direction: column; gap: 3px; overflow: hidden;">${parts.join('')}</div>
      </div>`;

  const side = `<div style="display: flex; flex-direction: column; gap: 16px; min-height: 0;">
        <div style="background: #fff; border: 1px solid #e2dfd8; border-radius: 8px; display: flex; flex-direction: column; overflow: hidden;">
          <div style="padding: 10px 14px; border-bottom: 1px solid #e2dfd8; font-size: 14px; font-weight: 500;">此決定類型的欄位規則</div>
          ${c.fields.map(([k,v,s])=>`<div class="fr"><div style="display:flex;gap:8px;align-items:center;"><div class="d ${s}"></div>${esc(k)}</div><div style="color:#6b6862;text-align:right;">${esc(v)}</div></div>`).join('')}
        </div>
        <div style="background: #fff; border: 1px solid #e2dfd8; border-radius: 8px; display: flex; flex-direction: column; overflow: hidden;">
          <div style="padding: 10px 14px; border-bottom: 1px solid #e2dfd8; font-size: 14px; font-weight: 500;">引據清單</div>
          ${c.refs.map(([k,v])=>`<div class="ref"><div class="k"><span>${esc(k)}</span><span class="ok">在檢索結果內</span></div><div class="v">${esc(v)}</div></div>`).join('')}
          <div style="padding: 8px 14px; background: #f7fafa; font-size: 11.5px; color: #1f5f6b;">條號皆來自已勾選法規，模型不得自行新增。</div>
        </div>
        <div style="margin-top: auto; display: flex; flex-direction: column; gap: 8px;">
          <div style="padding: 9px 16px; border-radius: 6px; border: 1px solid #e2dfd8; font-size: 13px; text-align: center;">重新生成理由段</div>
          <div style="padding: 9px 16px; border-radius: 6px; background: #1f5f6b; color: #fff; font-size: 13px; font-weight: 500; text-align: center;">送稽核</div>
        </div>
      </div>`;

  writeFileSync(c.file + '.tmp', shell(c, body, side));
  console.log('wrote', c.file);
}
