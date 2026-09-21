const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync("index.html", "utf8");
const logic = html.match(/function soldQty[\s\S]*?(?=function monthKey)/)[0];
const context = { schedule: [], Date };
vm.createContext(context);
vm.runInContext(logic, context);

assert.equal(context.recordStatus({ allocated: 0, status: "waiting", sales: [] }), "unallocated");
assert.equal(context.recordStatus({ allocated: 10, listingDate: "2999-01-01", sales: [] }), "listing");
assert.equal(context.recordStatus({ allocated: 10, listingDate: "2000-01-01", sales: [] }), "holding");
assert.equal(context.recordStatus({ allocated: 10, listingDate: null, status: "holding", sales: [] }), "listing");
assert.equal(context.recordStatus({ allocated: 10, legacy: true, listingDate: null, status: "holding", sales: [] }), "holding");
assert.equal(context.recordStatus({ allocated: 10, listingDate: "2000-01-01", sales: [{ qty: 5 }] }), "holding");
assert.equal(context.remain({ allocated: 10, sales: [{ qty: 5 }, { qty: 2 }] }), 3);
assert.equal(context.recordStatus({ allocated: 10, sales: [{ qty: 5 }, { qty: 5 }] }), "sold");
assert.equal(context.recordStatus({ allocated: 10, legacy: true, status: "sold", sales: [{ qty: null }] }), "sold");
assert.equal(context.recordStatus({ allocated: 150, legacy: true, status: "sold", sales: [] }), "holding");

assert(html.includes('r.sales[editingSaleIndex]=sale'), "existing sale must be replaced by index");
assert(html.includes('else r.sales.push(sale)'), "new split sale must append");
assert(!html.includes('!r.legacy||s.date||s.qty!=null'), "every legacy sale must expose its edit button");
assert(html.includes('document.getElementById("salePnl").value=""'), "new sale PnL must reset");
assert(html.includes('pnlText===""?null:Number(pnlText)'), "blank PnL must remain editable/null");
assert(html.includes('listingDate:s.listing||null'), "schedule listing date must be linked to a new record");
assert(html.includes('class="edit-sale-btn"'), "sale edit action must use the visible button style");
assert(html.includes('sheet:true'), "opening a popup must create a popup history state");
assert(html.includes('if(sheet.classList.contains("show"))closeSheet(true)'), "browser back must close the popup before rendering the underlying screen");
assert(html.includes('if(!fromHistory&&history.state?.sheet)history.back()'), "closing a popup must consume its history state");
assert(html.includes('records.filter(r=>`${r.name} ${r.broker} ${r.year}`'), "record search must cover every year, stock and broker");
assert(html.includes('전체 연도 검색 결과 ${arr.length}건'), "global search results must identify their scope");
assert(html.includes('r.sales.splice(index,1)'), "sale deletion must remove only the selected sale");
assert(html.includes('applyRecordStatus(r);persist()'), "sale deletion must recalculate status and persist immediately");
assert(html.includes('id="saleDeleteButton"'), "sale editing form must expose a delete action");

console.log("app status and sale logic OK");
