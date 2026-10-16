import {colors, spendColors, money, monthTitle, providerColor, safeText, textRow, weekdays, weekdayIndex, weekdayShort, widthOf, type Dataset, type Report, type Row} from './types.js';
const centered = (text: string, width: number): string => ' '.repeat(Math.floor((width - text.length) / 2)) + text + ' '.repeat(Math.ceil((width - text.length) / 2));
const wrapped = (text: string, width: number): Row[] => {
  const rows: Row[] = []; let line = '';
  for (const word of text.split(' ')) {if (line && line.length + word.length + 1 > width) {rows.push(textRow(line)); line = '';} line += (line ? ' ' : '') + word;}
  if (line) rows.push(textRow(line)); return rows;
};
export const NICE_STEPS = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10] as const;
export function budgetRow(report: Report, ascii = false): Row {
  const b = report.monthly_budget;
  const amount = !b.observed_requests ? 'unavailable' : b.observed_requests === b.unpriced_requests ? 'unpriced' : money(b.known_cost_usd);
  return textRow('Month ' + amount + ' / ' + money(b.budget_usd) + (b.observed_requests > b.unpriced_requests ? (ascii ? ' | ' : ' · ') + (100 * b.known_cost_usd / b.budget_usd).toFixed(1) + '%' : ''));
}
/** Width of the widest y-axis label for this report at this plot height. */
export function axisLabelWidth(report: Report, height: number): number {
  return Math.max(...axisLabels(report, height).labels.map(l => l.length));
}
function axisLabels(report: Report, height: number): {step: number; count: number; labels: string[]} {
  const maximum = Math.max(0, ...report.series.flatMap(s => s.daily.map(d => d.cost_usd ?? 0)));
  const target = (maximum || 1) / height, power = 10 ** Math.floor(Math.log10(target));
  const step = NICE_STEPS.map(n => n * power).find(n => n >= target)!;
  let precision = Math.max(0, -Math.floor(Math.log10(step))); if (Number(step.toFixed(precision)) !== step) precision++;
  return {step, count: height, labels: Array.from({length: height + 1}, (_, index) => '$' + ((height - index) * step).toLocaleString('en-US', {minimumFractionDigits: precision, maximumFractionDigits: precision}))};
}
/** `minLabelWidth` pads the y-axis so every month shares one plot origin and width. */
export function graphRows(report: Report, width: number, height: number, ascii = false, minLabelWidth = 0): Row[] {
  // Fixed row count keeps the plot height stable across months; finer nice steps keep
  // the top tick within a third of the maximum.
  const {step, count, labels} = axisLabels(report, height);
  const labelWidth = Math.max(minLabelWidth, ...labels.map(l => l.length)), available = Math.max(3, width - labelWidth - 3), days = report.period.days;
  // Three columns per day fit a number and weekday under every day. Narrower
  // terminals keep the whole month in one plot: two columns per day (odd day
  // numbers, a weekday initial per day), then one (weekly day numbers, initials).
  // Panels remain only for axis labels too wide for even one column per day.
  const minStride = available >= 3 * days ? 3 : available >= 2 * days ? 2 : 1;
  const fit = Math.max(1, Math.min(days, Math.floor(available / minStride))), panelDays = Math.ceil(days / Math.ceil(days / fit)), stride = Math.max(minStride, Math.floor(available / panelDays)), compact = stride < 3;
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
    if (stride === 1) {
      // One column per day: day numbers every week, a weekday initial under every day.
      const marks = Array.from({length: length + 1}, () => ' ');
      for (let index=start; index<start+length; index+=7) {const label = String(index+1).padStart(2,'0'); marks[index-start] = label[0]!; marks[index-start+1] = label[1]!;}
      numbers.push({text:marks.join('').trimEnd(),color:colors.muted});
    }
    for (let index=start; index<start+length; index++) {
      if (stride === 1) {
        const weekday = weekdayIndex(report.period.from.slice(0,8)+String(index+1).padStart(2,'0'));
        names.push({text:weekdayShort[weekday]![0]!,color:weekday===0||weekday===6 ? colors.amber : colors.muted});continue;
      }
      const date = report.period.from.slice(0,8)+String(index+1).padStart(2,'0'), weekday = weekdayIndex(date);
      numbers.push({text:compact ? (index % 2 === 0 ? String(index+1).padStart(2,'0') : '  ') : centered(String(index+1).padStart(2,'0'),stride),color:colors.muted});
      names.push({text:compact ? ' '+weekdayShort[weekday]![0]! : centered(weekdayShort[weekday]!,stride),color:weekday===0||weekday===6 ? colors.amber : colors.muted});
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
  return rows;
}
/** Whole dollars for narrow tables; a small positive amount never reads as $0. */
const dollars = (amount: number): string => amount > 0 && amount < .5 ? '<$1' : '$' + Math.round(amount).toLocaleString('en-US');
export function weekRows(report: Report, width: number, ascii = false): Row[] {
  const data = report.weekday_view, dash = ascii ? '-' : '—';
  // Widest layout whose weeks fit side by side: full weekday names and cents,
  // then three-letter names, then whole dollars; panels only after that.
  const layouts = [{name: 9, cents: true}, {name: 5, cents: true}, {name: 5, cents: false}].map(layout => {
    const format = layout.cents ? money : dollars;
    const amount = (cell: typeof data.rows[number]['cells'][number]): string => !cell.in_month ? '' : (cell.cost_usd !== null ? format(cell.cost_usd) : cell.observations ? '?' : dash);
    const totalAmount = (total: typeof data.totals[number]): string => total.cost_usd!==null?format(total.cost_usd):total.observations?'?':dash;
    const cellWidth = Math.max(layout.cents ? 11 : 7, ...data.rows.flatMap(row=>row.cells.map(c=>amount(c).length+(layout.cents?3:2))), ...data.totals.map(total=>totalAmount(total).length+(layout.cents?3:2)));
    return {...layout, amount, totalAmount, cellWidth, label: layout.name + 2};
  });
  const layout = layouts.find(l => l.label + data.weeks.length * l.cellWidth <= width) ?? layouts.at(-1)!;
  const {amount, totalAmount, cellWidth, label} = layout, perPanel = Math.max(1, Math.floor((width - label) / cellWidth));
  const name = (text: string): string => (layout.name === 5 && text !== 'Total' ? text.slice(0, 3) : text).padEnd(layout.name) + '  ';
  const rows: Row[] = [textRow('Cost by Weekday'+(ascii?' | ':' · ')+monthTitle(report.period.from),colors.text,true),[],...wrapped(data.providers.map(safeText).join(', ')+' ('+(data.basis==='api_equivalent_estimate'?'API estimates':'reported cost')+')',width),[]];
  for (let start=0;start<data.weeks.length;start+=perPanel) {
    rows.push(textRow(' '.repeat(label)+data.weeks.slice(start,start+perPanel).map(w=>centered(w.from.slice(-2)+(ascii?'-':'–')+w.to.slice(-2),cellWidth)).join('')));
    data.rows.forEach((row,index)=> {
      const segments: Row = [{text:name(weekdays[index]!),color:index===0||index===6?colors.amber:colors.muted}];
      for (const cell of row.cells.slice(start,start+perPanel)) segments.push({text:amount(cell).padStart(cellWidth-2)+'  ',color:cell.intensity_level===null?colors.muted:spendColors[cell.intensity_level]!,bold:cell.intensity_level===4});
      rows.push(segments);
    });
    rows.push([{text:name('Total'),color:colors.text,bold:true},...data.totals.slice(start,start+perPanel).map(total=>({text:totalAmount(total).padStart(cellWidth-2)+'  ',color:colors.text,bold:true}))],[]);
  }
  rows.push([{text:'Spend: low ',color:colors.muted},...spendColors.map(color=>({text:ascii?'* ':'● ',color})),{text:'high',color:colors.muted}],budgetRow(report,ascii),[],textRow('Insights',colors.text,true));
  for(const message of report.insights.messages) rows.push(...wrapped(safeText(message),width));
  return rows;
}
/** Largest plot height (<= options.height) at which this report fits the terminal. */
export function fittedHeight(report: Report, options: Dataset['options'], columns: number, lines: number): number {
  const width = Math.max(48,Math.min(240,options.width??columns));
  for (let height = options.height; height > 4; height--) if (graphRows(report,width,height,options.ascii).length <= lines-3) return height;
  return 4;
}
export function frame(report: Report, view: 'graph'|'weeks', options: Dataset['options'], columns: number, lines: number, stableHeight?: number, labelWidth = 0): Row[] {
  const width=Math.max(48,Math.min(240,options.width??columns)); let height=stableHeight??options.height;
  let rows = view==='weeks'?weekRows(report,width,options.ascii):graphRows(report,width,height,options.ascii,labelWidth);
  while(rows.length>lines-3) {
    const compact=rows.filter(row=>widthOf(row)>0);
    if(compact.length<=lines-3) return compact;
    if(view==='weeks'||height<=4) return [textRow(report.period.from.slice(0,7)+': enlarge the terminal or use --snapshot.'),textRow('W switches views; this view needs '+(compact.length+3)+' rows.')];
    height--;rows=graphRows(report,width,height,options.ascii,labelWidth);
  }
  return rows;
}
