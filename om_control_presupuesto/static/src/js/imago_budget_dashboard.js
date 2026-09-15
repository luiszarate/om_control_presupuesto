odoo.define("om_control_presupuesto.dashboard", function (require) {
    "use strict";

    var AbstractAction = require("web.AbstractAction");
    var core = require("web.core");

    var QWeb = core.qweb;
    var actionRegistry = core.action_registry;

    var ImagoBudgetDashboard = AbstractAction.extend({
        className: "o_imago_dashboard",

        events: {
            "change .o_imago_budget_filter": "_onBudgetChanged",
            "change .o_imago_month_filter": "_onMonthChanged",
            "change .o_imago_category_filter": "_onCategoryChanged",
            "click .o_imago_category_row": "_onOpenCategory",
            "click .o_imago_open_detail": "_onOpenDetail",
            "click .o_imago_open_summary": "_onOpenSummary",
            "click .o_imago_export": "_onExport",
        },

        init: function (parent, action) {
            this._super.apply(this, arguments);
            this.action = action;
            this.data = {};
            this.budgetId = false;
            this.cutoffMonth = false;
            this.categoryId = false;
        },

        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this._loadData()]);
        },

        start: function () {
            this._renderDashboard();
            return this._super.apply(this, arguments);
        },

        _loadData: function () {
            var self = this;
            return this._rpc({
                model: "imago.budget.report.wizard",
                method: "get_dashboard_data",
                args: [this.budgetId || false, this.cutoffMonth || false, this.categoryId || false],
            }).then(function (data) {
                self.data = data;
                self.budgetId = data.selected_budget_id || false;
                self.cutoffMonth = data.selected_cutoff_month || false;
                self.categoryId = data.selected_category_id || false;
            });
        },

        _reload: function () {
            var self = this;
            this.$el.addClass("o_imago_loading");
            return this._loadData().then(function () {
                self._renderDashboard();
            });
        },

        _renderDashboard: function () {
            this.$el.removeClass("o_imago_loading");
            this.$el.html(QWeb.render("ImagoBudgetDashboard", {widget: this}));
            this._renderLineChart();
        },

        _onBudgetChanged: function (event) {
            this.budgetId = parseInt(event.currentTarget.value, 10) || false;
            this.cutoffMonth = false;
            this.categoryId = false;
            return this._reload();
        },

        _onMonthChanged: function (event) {
            this.cutoffMonth = parseInt(event.currentTarget.value, 10) || 1;
            return this._reload();
        },

        _onCategoryChanged: function (event) {
            this.categoryId = parseInt(event.currentTarget.value, 10) || false;
            return this._reload();
        },

        _reportContext: function (categoryId) {
            return {
                default_budget_id: this.budgetId,
                default_cutoff_month: String(this.cutoffMonth),
                default_category_id: categoryId === undefined ? this.categoryId : categoryId,
            };
        },

        _onOpenCategory: function (event) {
            var categoryId = parseInt(event.currentTarget.dataset.categoryId, 10) || false;
            return this._openSummary(categoryId);
        },

        _onOpenSummary: function () {
            return this._openSummary(this.categoryId);
        },

        _openSummary: function (categoryId) {
            return this.do_action({
                type: "ir.actions.act_window",
                name: "Resumen mensual",
                res_model: "imago.budget.report.wizard",
                views: [[false, "form"]],
                view_mode: "form",
                target: "current",
                context: this._reportContext(categoryId),
            });
        },

        _onOpenDetail: function () {
            var self = this;
            return this._rpc({
                model: "imago.budget.report.wizard",
                method: "create",
                args: [{
                    budget_id: this.budgetId,
                    cutoff_month: String(this.cutoffMonth),
                    category_id: this.categoryId || false,
                }],
            }).then(function (wizardId) {
                return self._rpc({
                    model: "imago.budget.report.wizard",
                    method: "action_calculate",
                    args: [[wizardId]],
                }).then(function () { return wizardId; });
            }).then(function (wizardId) {
                return self._rpc({
                    model: "imago.budget.report.wizard",
                    method: "action_view_purchase_lines",
                    args: [[wizardId]],
                });
            }).then(function (action) {
                return self.do_action(action);
            });
        },

        _onExport: function () {
            var self = this;
            return this._rpc({
                model: "imago.budget.report.wizard",
                method: "create",
                args: [{
                    budget_id: this.budgetId,
                    cutoff_month: String(this.cutoffMonth),
                    category_id: this.categoryId || false,
                    include_subcategories: true,
                }],
            }).then(function (wizardId) {
                return self._rpc({
                    model: "imago.budget.report.wizard",
                    method: "action_export_xlsx",
                    args: [[wizardId]],
                });
            }).then(function (action) {
                return self.do_action(action);
            });
        },

        formatMoney: function (value) {
            if (value === null || value === undefined) {
                return "N/A";
            }
            return new Intl.NumberFormat("es-MX", {
                style: "currency",
                currency: "MXN",
                minimumFractionDigits: 2,
            }).format(value);
        },

        formatPercent: function (value) {
            if (value === null || value === undefined) {
                return "N/A";
            }
            return new Intl.NumberFormat("es-MX", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            }).format(value) + "%";
        },

        barWidth: function (value) {
            var rows = (this.data.report && this.data.report.rows) || [];
            var maxValue = 1;
            rows.forEach(function (row) {
                maxValue = Math.max(maxValue, row.authorized || 0, row.spent || 0, row.projection || 0);
            });
            return Math.max(0, Math.min(100, (value || 0) / maxValue * 100)).toFixed(2) + "%";
        },

        statusLabel: function (status) {
            return {
                incomplete: "Incompleto",
                unbudgeted: "Sin presupuesto",
                over: "Excedido",
                risk: "Riesgo al cierre",
                within: "Dentro del presupuesto",
            }[status] || status;
        },

        _renderLineChart: function () {
            var svg = this.el.querySelector(".o_imago_line_chart");
            if (!svg || !this.data.report) {
                return;
            }
            var namespace = "http://www.w3.org/2000/svg";
            var points = this.data.report.cumulative || [];
            var values = [];
            points.forEach(function (point) {
                [point.observed, point.reference, point.projected].forEach(function (value) {
                    if (value !== null) {
                        values.push(value);
                    }
                });
            });
            var maxValue = Math.max.apply(Math, values.concat([1]));
            var x = function (month) { return 42 + (month - 1) * 59.5; };
            var y = function (value) { return 205 - (value / maxValue) * 170; };
            var create = function (name, attributes) {
                var node = document.createElementNS(namespace, name);
                Object.keys(attributes).forEach(function (key) {
                    node.setAttribute(key, attributes[key]);
                });
                svg.appendChild(node);
                return node;
            };
            [0, 0.5, 1].forEach(function (ratio) {
                create("line", {x1: 42, y1: 205 - ratio * 170, x2: 696, y2: 205 - ratio * 170, class: "o_imago_grid"});
            });
            points.forEach(function (point) {
                var label = create("text", {x: x(point.month), y: 226, class: "o_imago_axis_label"});
                label.textContent = point.month;
            });
            var drawSeries = function (key, className) {
                var series = points.filter(function (point) { return point[key] !== null; });
                if (!series.length) {
                    return;
                }
                create("polyline", {
                    points: series.map(function (point) { return x(point.month) + "," + y(point[key]); }).join(" "),
                    class: className,
                });
            };
            drawSeries("reference", "o_imago_line_reference");
            drawSeries("observed", "o_imago_line_observed");
            drawSeries("projected", "o_imago_line_projected");
        },
    });

    actionRegistry.add("imago_budget_dashboard", ImagoBudgetDashboard);
    return ImagoBudgetDashboard;
});
