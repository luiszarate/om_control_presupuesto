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
            "click .o_imago_dismiss_issue": "_onDismissIssue",
            "click .o_imago_restore_issue": "_onRestoreIssue",
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
            this.$el.addClass("o_imago_loading").attr("aria-busy", "true");
            return this._loadData().then(function () {
                self._renderDashboard();
            }, function (error) {
                self.$el.removeClass("o_imago_loading").attr("aria-busy", "false");
                throw error;
            });
        },

        _renderDashboard: function () {
            // AbstractAction can replace className with o_action during init.
            // Apply the style scope to the actual action root on every render.
            this.$el.addClass("o_imago_dashboard").removeClass("o_imago_loading").attr("aria-busy", "false");
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

        _filters: function (categoryId) {
            return {
                budget_id: this.budgetId,
                cutoff_month: this.cutoffMonth,
                category_id: categoryId === undefined ? this.categoryId : categoryId,
            };
        },

        _runSummaryAction: function (method, categoryId) {
            var self = this;
            return this._rpc({
                model: "imago.budget.report.wizard",
                method: method,
                args: [this._filters(categoryId)],
            }).then(function (action) {
                return self.do_action(action);
            });
        },

        _onOpenCategory: function (event) {
            var categoryId = parseInt(event.currentTarget.dataset.categoryId, 10) || false;
            return this._runSummaryAction("action_open_summary", categoryId);
        },

        _onOpenSummary: function () {
            return this._runSummaryAction("action_open_summary");
        },

        _onOpenDetail: function () {
            return this._runSummaryAction("action_open_purchase_detail");
        },

        _onExport: function () {
            return this._runSummaryAction("action_export_summary");
        },

        _issueFromEvent: function (event, listName) {
            var index = parseInt(event.currentTarget.dataset.issueIndex, 10);
            var report = this.data.report || {};
            return (report[listName] || [])[index];
        },

        _onDismissIssue: function (event) {
            var self = this;
            var issue = this._issueFromEvent(event, "issue_items");
            if (!issue) {
                return;
            }
            var message = "Descartar la incidencia?\n\n" + issue.title +
                "\n\nDejara de marcar el reporte como incompleto.";
            if (!window.confirm(message)) {
                return;
            }
            return this._rpc({
                model: "imago.budget.report.wizard",
                method: "dismiss_report_issue",
                args: [this.budgetId, issue.item_keys, issue.title],
            }).then(function () {
                return self._reload();
            });
        },

        _onRestoreIssue: function (event) {
            var self = this;
            var issue = this._issueFromEvent(event, "dismissed_issue_items");
            if (!issue) {
                return;
            }
            return this._rpc({
                model: "imago.budget.report.wizard",
                method: "restore_report_issue",
                args: [this.budgetId, issue.item_keys],
            }).then(function () {
                return self._reload();
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

        hasAttentionRows: function () {
            return this.data.report.rows.some(function (row) {
                return row.status !== "within";
            });
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
            var minValue = Math.min.apply(Math, values.concat([0]));
            var x = function (month) { return 76 + (month - 1) * 56; };
            var y = function (value) { return 256 - ((value - minValue) / (maxValue - minValue)) * 216; };
            var months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
            var self = this;
            var create = function (name, attributes) {
                var node = document.createElementNS(namespace, name);
                Object.keys(attributes).forEach(function (key) {
                    node.setAttribute(key, attributes[key]);
                });
                svg.appendChild(node);
                return node;
            };
            var unit = create("text", {x: 76, y: 18, class: "o_imago_axis_unit"});
            unit.textContent = "MXN";
            [0, 0.25, 0.5, 0.75, 1].forEach(function (ratio) {
                var value = minValue + ratio * (maxValue - minValue);
                create("line", {x1: 76, y1: y(value), x2: 692, y2: y(value), class: "o_imago_grid"});
                var label = create("text", {x: 64, y: y(value) + 4, class: "o_imago_value_label"});
                label.textContent = new Intl.NumberFormat("es-MX", {maximumFractionDigits: 1}).format(
                    Math.abs(value) >= 1000000 ? value / 1000000 : Math.abs(value) >= 1000 ? value / 1000 : value
                ) + (Math.abs(value) >= 1000000 ? " M" : Math.abs(value) >= 1000 ? " mil" : "");
            });
            points.forEach(function (point) {
                var label = create("text", {x: x(point.month), y: 282, class: "o_imago_axis_label"});
                label.textContent = months[point.month - 1];
            });
            var drawSeries = function (key, className, color) {
                var series = points.filter(function (point) { return point[key] !== null; });
                if (!series.length) {
                    return;
                }
                create("polyline", {
                    points: series.map(function (point) { return x(point.month) + "," + y(point[key]); }).join(" "),
                    class: className,
                    fill: "none",
                    stroke: color,
                    "stroke-width": 3,
                });
                series.forEach(function (point) {
                    var dot = create("circle", {cx: x(point.month), cy: y(point[key]), r: 3, fill: color});
                    var title = document.createElementNS(namespace, "title");
                    title.textContent = months[point.month - 1] + ": " + self.formatMoney(point[key]);
                    dot.appendChild(title);
                });
            };
            drawSeries("reference", "o_imago_line_reference", "#8797a8");
            drawSeries("observed", "o_imago_line_observed", "#2f75b5");
            drawSeries("projected", "o_imago_line_projected", "#c56920");
        },
    });

    actionRegistry.add("imago_budget_dashboard", ImagoBudgetDashboard);
    return ImagoBudgetDashboard;
});
