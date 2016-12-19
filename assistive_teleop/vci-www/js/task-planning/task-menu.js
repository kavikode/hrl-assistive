var RFH = (function (module) {
    module.TaskMenu = function (options) {
        "use strict";
        var self = this;
        self.div = $('#'+ options.divId);
        var ros = options.ros;
        self.domains = {};

        var hideAllOptions = function () {
            var handles = $('#task-menu select.option-select');
            for (var i=0; i<handles.length; i += 1) {
                $(handles[i]).selectmenu('widget').hide();
            }
            $('label.option-select').hide();  // Hide labels
        };

        var showOptions = function (domain) {
            var handles = $('#task-menu select.option-select.option-'+domain);
            for (var i=0; i<handles.length; i += 1) {
                $(handles[i]).selectmenu('widget').show();
            }
            $('label.option-select.option-'+domain).show();  // show labels
        };

        self.updateOptions = function (event) {
            // Update to show/hide appropriate option select boxes when domain is changed
            hideAllOptions();
            var domain = $('#domain-select :selected').val();
            showOptions(domain);
        };
        
        var getActiveOptions = function (domain) {
            var options = {};
            var handles = $('#task-menu select.option-select.option-'+domain);
            for (var i=0; i<handles.length; i += 1) {
                options[handles[i].id.replace('-select','')] = $(handles[i]).val();    
            }
            return options;
        };

        var startTask = function (event) {
            var domain = $('#domain-select :selected').val();
            var options = getActiveOptions(domain);
            console.log(options)
            self.domains[domain].sendTaskGoal(options);
        };

        $('#domain-select').on('selectmenuchange.rfh', self.updateOptions);
        $('#start-task-button').button().on('click.rfh', startTask);
    };

    module.initTaskMenu = function () {
        /* Create Menu and apply styling */
        RFH.taskMenu = new RFH.TaskMenu({divId: 'task-menu',
                                         ros: RFH.ros});
        $('#domain-select').selectmenu({collapsible:true});
        $('#task-menu select.option-select').selectmenu().hide();

        /* Add Domain instances to menu domains */
        RFH.taskMenu.domains.adl = new RFH.Domains.ADL({ros:RFH.ros});
        
        /* Update menu to reflect current state */
        RFH.taskMenu.updateOptions();
    };
    return module;
})(RFH || {});
