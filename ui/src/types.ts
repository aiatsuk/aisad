export type View = 'graph' | 'weeks';
export type Day = {date: string; cost_usd: number | null; observations: number; unpriced_observations: number; incomplete: boolean};
export type Series = {provider: string; basis: string; daily: Day[]; known_cost_usd: number; observations: number; unpriced_observations: number; incomplete: boolean};
export type WeekCell = Day & {in_month: boolean; future: boolean; intensity_level: number | null};
export type WeekTotal = {cost_usd: number | null; observations: number; unpriced_observations: number; incomplete: boolean};
export type Budget = {known_cost_usd: number; budget_usd: number; observed_requests: number; unpriced_requests: number; pricing_complete: boolean};
export type Report = {period: {from: string; to: string; days: number}; series: Series[]; monthly_budget: Budget; weekday_view: {basis: string; providers: string[]; weeks: {from: string; to: string}[]; rows: {weekday: string; cells: WeekCell[]}[]; totals: WeekTotal[]}; insights: {messages: string[]}};
export type Dataset = {schema_version: 1; initial_month: string; initial_view: View; options: {color: boolean; ascii: boolean; width: number | null; height: number}; months: {month: string; report: Report}[]};
export type Segment = {text: string; color?: string; bold?: boolean};
export type Row = Segment[];
export type State = {index: number; view: View};
export type Action = 'previous' | 'next' | 'toggle';
export const weekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'] as const;
export const weekdayShort = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'] as const;
export const colors = {muted: '#707070', text: '#cccccc', coral: '#d77757', lavender: '#a5a9ff', amber: '#e5b567'};
export const spendColors = [colors.text, '#d4ad9b', colors.coral, '#e59b59', colors.amber] as const;
export const money = (amount: number): string => '$' + amount.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
export const safeText = (text: string): string => text.replace(/[\x00-\x1f\x7f-\x9f]/g, ' ');
export const monthTitle = (from: string): string => new Intl.DateTimeFormat('en-US', {month: 'short', year: 'numeric', timeZone: 'UTC'}).format(new Date(from + 'T00:00:00Z'));
export const weekdayIndex = (date: string): number => new Date(date + 'T00:00:00Z').getUTCDay();
export const textRow = (text: string, color = colors.muted, bold = false): Row => [{text, color, bold}];
export const widthOf = (row: Row): number => row.reduce((sum, segment) => sum + [...segment.text].length, 0);
export const providerColor = (name: string): string => ({Claude: colors.coral, Codex: colors.lavender, Grok: colors.amber}[name] ?? '#70c7c7');

export function navigate(state: State, action: Action, count: number): State {
  if (action === 'toggle') return {...state, view: state.view === 'graph' ? 'weeks' : 'graph'};
  return {...state, index: Math.max(0, Math.min(count - 1, state.index + (action === 'previous' ? -1 : 1)))};
}

const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const date = (value: unknown): value is string => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value));
const day = (value: unknown): boolean => object(value) && date(value.date) && (value.cost_usd === null || finite(value.cost_usd)) && finite(value.observations) && finite(value.unpriced_observations) && typeof value.incomplete === 'boolean';
function report(value: unknown): boolean {
  if (!object(value) || !object(value.period) || !date(value.period.from) || !date(value.period.to) || !Number.isInteger(value.period.days) || Number(value.period.days) < 28 || Number(value.period.days) > 31 || !Array.isArray(value.series)) return false;
  if (!value.series.every(item => object(item) && typeof item.provider === 'string' && typeof item.basis === 'string' && finite(item.known_cost_usd) && finite(item.observations) && finite(item.unpriced_observations) && typeof item.incomplete === 'boolean' && Array.isArray(item.daily) && item.daily.length === (value.period as Record<string, unknown>).days && item.daily.every(day))) return false;
  const budget = value.monthly_budget, weekly = value.weekday_view;
  if (!object(weekly) || !Array.isArray(weekly.totals) || !Array.isArray(weekly.weeks) || weekly.totals.length!==weekly.weeks.length || !weekly.totals.every(total=>object(total) && (total.cost_usd===null||finite(total.cost_usd)) && finite(total.observations) && finite(total.unpriced_observations) && typeof total.incomplete==='boolean') || !object(value.insights) || !Array.isArray(value.insights.messages) || !value.insights.messages.every(message=>typeof message==='string')) return false;
  return object(budget) && finite(budget.known_cost_usd) && finite(budget.budget_usd) && budget.budget_usd > 0 && finite(budget.observed_requests) && finite(budget.unpriced_requests) && typeof budget.pricing_complete === 'boolean' && object(weekly) && typeof weekly.basis === 'string' && Array.isArray(weekly.providers) && weekly.providers.every(p => typeof p === 'string') && Array.isArray(weekly.weeks) && weekly.weeks.length >= 4 && weekly.weeks.length <= 6 && weekly.weeks.every(w => object(w) && date(w.from) && date(w.to)) && Array.isArray(weekly.rows) && weekly.rows.length === 7 && weekly.rows.every((row, index) => object(row) && row.weekday === weekdays[index] && Array.isArray(row.cells) && row.cells.length === (weekly.weeks as unknown[]).length && row.cells.every(cell => day(cell) && object(cell) && typeof cell.in_month === 'boolean' && typeof cell.future === 'boolean' && (cell.cost_usd === null ? cell.intensity_level === null : Number.isInteger(cell.intensity_level) && Number(cell.intensity_level)>=0 && Number(cell.intensity_level)<=4)));
}
export function parseDataset(value: unknown): Dataset {
  if (!object(value) || value.schema_version !== 1 || typeof value.initial_month !== 'string' || !['graph', 'weeks'].includes(String(value.initial_view)) || !object(value.options) || typeof value.options.color !== 'boolean' || typeof value.options.ascii !== 'boolean' || !(value.options.width === null || (finite(value.options.width) && value.options.width >= 48 && value.options.width <= 240)) || !finite(value.options.height) || value.options.height < 4 || value.options.height > 30 || !Array.isArray(value.months) || !value.months.length || !value.months.every(item => object(item) && typeof item.month === 'string' && /^\d{4}-\d{2}$/.test(item.month) && report(item.report))) throw new Error('Invalid AISAD aggregate UI dataset');
  const dataset = value as Dataset;
  if (!dataset.months.some(item => item.month === dataset.initial_month) || dataset.months.some((item, index) => item.month !== item.report.period.from.slice(0, 7) || (index > 0 && item.month <= dataset.months[index - 1]!.month))) throw new Error('Invalid AISAD month ordering');
  return dataset;
}
