import {colors, money, monthTitle, providerColor, safeText, textRow, weekdays, weekdayIndex, weekdayShort, widthOf, type Dataset, type Report, type Row} from './types.js';
const centered = (text: string, width: number): string => ' '.repeat(Math.floor((width - text.length) / 2)) + text + ' '.repeat(Math.ceil((width - text.length) / 2));
const wrapped = (text: string, width: number): Row[] => {
  const rows: Row[] = []; let line = '';
  for (const word of text.split(' ')) {if (line && line.length + word.length + 1 > width) {rows.push(textRow(line)); line = '';} line += (line ? ' ' : '') + word;}
  if (line) rows.push(textRow(line)); return rows;
};
export function budgetRow(report: Report, ascii = false): Row {
  const b = report.monthly_budget;
  const amount = !b.observed_requests ? 'unavailable' : b.observed_requests === b.unpriced_requests ? 'unpriced' : money(b.known_cost_usd);
  return textRow('Month ' + amount + ' / ' + money(b.budget_usd) + (b.observed_requests > b.unpriced_requests ? (ascii ? ' | ' : ' · ') + (100 * b.known_cost_usd / b.budget_usd).toFixed(1) + '%' : ''));
}
export function graphRows(report: Report, width: number, height: number, ascii = false): Row[] {
  const maximum = Math.max(0, ...report.series.flatMap(s => s.daily.map(d => d.cost_usd ?? 0)));
  const target = (maximum || 1) / height, power = 10 ** Math.floor(Math.log10(target));
  const step = [1, 2, 2.5, 5, 10].map(n => n * power).find(n => n >= target)!;
  const count = Math.max(1, Math.ceil((maximum || 1) / step));
  let precision = Math.max(0, -Math.floor(Math.log10(step))); if (Number(step.toFixed(precision)) !== step) precision++;
  const labels = Array.from({length: count + 1}, (_, index) => '$' + ((count - index) * step).toLocaleString('en-US', {minimumFractionDigits: precision, maximumFractionDigits: precision}));
  const labelWidth = Math.max(...labels.map(l => l.length)), available = Math.max(3, width - labelWidth - 3), days = report.period.days;
  const panelDays = Math.max(1, Math.min(days, Math.floor(available / 3))), stride = Math.max(3, Math.floor(available / panelDays));
  const rows: Row[] = [textRow('Cost per Day' + (ascii ? ' | ' : ' · ') + monthTitle(report.period.from), colors.text, true), []];
  const glyphs: Record<number, string> = {0:'╶',1:'─',2:'─',3:'─',4:'│',8:'│',12:'│',5:'╯',6:'╰',9:'╮',10:'╭',7:'┴',11:'┬',13:'┤',14:'├',15:'┼'};
  for (let start = 0; start < days; start += panelDays) {
    const length = Math.min(panelDays, days - start), grid = Array.from({length: count + 1}, () => Array.from({length: length * stride}, () => new Map<number, {mask: number; unknown: boolean}>()));
    const put = (y: number, x: number, owner: number, mask = 0, unknown = false): void => {const cell = grid[y]![x]!, old = cell.get(owner) ?? {mask:0, unknown:false}; cell.set(owner, {mask: old.mask | mask, unknown: old.unknown || unknown});};
    const connect = (y1: number, x1: number, y2: number, x2: number, owner: number): void => {
      if (y1 === y2) for (let x = x1; x < x2; x++) {put(y1, x, owner, 2); put(y1, x + 1, owner, 1);}
      else for (let y = Math.min(y1, y2); y < Math.max(y1, y2); y++) {put(y, x1, owner, 8); put(y + 1, x1, owner, 4);}
    };
    report.series.forEach((series, owner) => {
      const values = series.daily.slice(start, start + length);
      values.forEach((day, index) => {
        const x = index * stride + Math.floor(stride / 2);
        if (day.cost_usd === null) {if (day.observations) put(count, x, owner, 0, true); return;}
        const y = count - Math.min(count, Math.max(0, Math.floor(day.cost_usd / step + .5)));
        put(y,x,owner); connect(y,x,y,(index+1)*stride-1,owner);
        const next = values[index + 1];
        if (next && next.cost_usd !== null) {const nx = (index+1)*stride+Math.floor(stride/2), ny = count-Math.min(count,Math.max(0,Math.floor(next.cost_usd/step+.5))); connect(y,x,y,nx,owner); connect(y,nx,ny,nx,owner);}
      });
    });
    if (panelDays < days) rows.push(textRow('Days ' + String(start+1).padStart(2,'0') + (ascii ? '-' : '–') + String(start+length).padStart(2,'0')));
    grid.forEach((line,y) => {
      const row: Row = [{text:labels[y]!.padStart(labelWidth)+' '+(ascii ? '|' : y === count ? '┼' : '┤')+' ', color:colors.muted}];
      for (const cell of line) {
        if (!cell.size) {row.push({text:' '}); continue;}
        const owner = Math.max(...cell.keys()), {mask,unknown} = cell.get(owner)!;
        const glyph = unknown ? '?' : ascii ? mask === 0 ? '*' : [1,2,3].includes(mask) ? '-' : [4,8,12].includes(mask) ? '|' : '+' : glyphs[mask]!;
        row.push({text:glyph, color:providerColor(report.series[owner]!.provider)});
      }
      while (row.at(-1)?.text === ' ') row.pop(); rows.push(row);
    });
    const prefix = ' '.repeat(labelWidth+3), numbers: Row = [{text:prefix,color:colors.muted}], names: Row = [{text:prefix,color:colors.muted}];
    for (let index=start; index<start+length; index++) {
      const date = report.period.from.slice(0,8)+String(index+1).padStart(2,'0'), weekday = weekdayIndex(date);
      numbers.push({text:centered(String(index+1).padStart(2,'0'),stride),color:colors.muted});
      names.push({text:centered(weekdayShort[weekday]!,stride),color:weekday===0||weekday===6 ? colors.amber : colors.muted});
    }
    rows.push(numbers,names,[]);
  }
  let legend: Row = [];
  for (const series of report.series) {
    const amount = !series.observations ? 'unavailable' : series.observations === series.unpriced_observations ? 'unpriced' : money(series.known_cost_usd);
    const label = (ascii ? '*' : '●')+' '+safeText(series.provider)+' '+amount+(series.basis==='provider_reported_turn_cost' ? ' (reported)' : '');
    if (legend.length && widthOf(legend)+3+label.length>width) {rows.push(legend);legend=[];}
    if (legend.length) legend.push({text:ascii ? ' | ' : ' · '}); legend.push({text:label,color:providerColor(series.provider)});
  }
  if (legend.length) rows.push(legend); rows.push([],budgetRow(report,ascii));
  if (!report.series.some(s => s.daily.some(d => d.cost_usd !== null))) rows.push(textRow('No priced daily observations for this month.'));
  const missing = report.series.reduce((sum,s) => sum+s.unpriced_observations,0);
  rows.push(...wrapped('Known API estimates; gaps/future days stay blank.' + (missing ? ' ? = unpriced ('+missing.toLocaleString('en-US')+' observations).' : report.series.some(s=>s.incomplete) ? ' Pricing is incomplete.' : ''),width));
  return rows;
}
export function weekRows(report: Report, width: number, ascii = false): Row[] {
  const data = report.weekday_view, amount = (cell: typeof data.rows[number]['cells'][number]): string => !cell.in_month ? '' : (cell.cost_usd !== null ? money(cell.cost_usd) : cell.observations ? '?' : ascii ? '-' : '—');
  const cellWidth = Math.max(11,...data.rows.flatMap(row=>row.cells.map(c=>amount(c).length+3))), perPanel = Math.max(1,Math.floor((width-11)/cellWidth));
  const maximum = Math.max(0,...data.rows.flatMap(r=>r.cells.map(c=>c.cost_usd??0)));
  const rows: Row[] = [textRow('Cost by Weekday'+(ascii?' | ':' · ')+monthTitle(report.period.from),colors.text,true),[],...wrapped(data.providers.map(safeText).join(', ')+' ('+(data.basis==='api_equivalent_estimate'?'API estimates':'reported cost')+')',width),[]];
  for (let start=0;start<data.weeks.length;start+=perPanel) {
    rows.push(textRow(' '.repeat(11)+data.weeks.slice(start,start+perPanel).map(w=>centered(w.from.slice(-2)+(ascii?'-':'–')+w.to.slice(-2),cellWidth)).join('')));
    data.rows.forEach((row,index)=> {
      const segments: Row = [{text:weekdays[index]!.padEnd(9)+'  ',color:index===0||index===6?colors.amber:colors.muted}];
      for (const cell of row.cells.slice(start,start+perPanel)) segments.push({text:amount(cell).padStart(cellWidth-2)+'  ',color:cell.cost_usd===null?colors.muted:cell.cost_usd===maximum&&maximum>0?colors.amber:colors.coral,bold:cell.cost_usd===maximum&&maximum>0});
      rows.push(segments);
    }); rows.push([]);
  }
  rows.push(budgetRow(report,ascii),...wrapped('Each cell: daily cost. '+(ascii?'-':'—')+' = no priced data; ? = unpriced.',width));
  if(data.rows.some(row=>row.cells.some(cell=>cell.incomplete))) rows.push(...wrapped('Known subtotals; incomplete pricing remains in JSON.',width));
  return rows;
}
export function frame(report: Report, view: 'graph'|'weeks', options: Dataset['options'], columns: number, lines: number): Row[] {
  const width = Math.max(48,Math.min(240,options.width??columns)); let height=options.height;
  let rows = view==='weeks'?weekRows(report,width,options.ascii):graphRows(report,width,height,options.ascii);
  while(rows.length>lines-3) {
    const compact=rows.filter(row=>widthOf(row)>0);
    if(compact.length<=lines-3) return compact;
    if(view==='weeks'||height<=4) return [textRow(report.period.from.slice(0,7)+': enlarge the terminal or use --snapshot.'),textRow('W switches views; this view needs '+(compact.length+3)+' rows.')];
    height--;rows=graphRows(report,width,height,options.ascii);
  }
  return rows;
}
