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
assert.equal(context.recordStatus({ allocated: 10, listingDate: "2000-01-01", sales: [{ qty: 5 }] }), "holding");
assert.equal(context.remain({ allocated: 10, sales: [{ qty: 5 }, { qty: 2 }] }), 3);
assert.equal(context.recordStatus({ allocated: 10, sales: [{ qty: 5 }, { qty: 5 }] }), "sold");
assert.equal(context.recordStatus({ allocated: 10, legacy: true, status: "sold", sales: [{ qty: null }] }), "sold");

assert(html.includes('r.sales[editingSaleIndex]=sale'), "existing sale must be replaced by index");
assert(html.includes('else r.sales.push(sale)'), "new split sale must append");
assert(html.includes('document.getElementById("salePnl").value=""'), "new sale PnL must reset");
assert(html.includes('pnlText===""?null:Number(pnlText)'), "blank PnL must remain editable/null");
assert(html.includes('listingDate:s.listing||null'), "schedule listing date must be linked to a new record");

console.log("app status and sale logic OK");
