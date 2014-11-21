RFH.CartesianEEControl = function (options) {
    'use strict';
    var self = this;
    self.div = options.div || 'markers';
    self.arm = options.arm;
    self.gripper = options.gripper;
    self.smooth = self.arm instanceof PR2ArmJTTask;
    self.tfClient = options.tfClient;
    self.camera = options.camera;
    self.buttonText = self.arm.side[0] === 'r' ? 'Right_Hand' : 'Left_Hand';
    self.buttonClass = 'hand-button';
    self.posCtrlId = self.arm.side[0]+'CtrlIcon';
    self.targetIcon = new RFH.EECartControlIcon({divId: self.posCtrlId,
                                                 parentId: self.div,
                                                 arm: self.arm,
                                                 smooth: self.smooth});
    var handCtrlCSS = {bottom:"6%"};
    handCtrlCSS[self.arm.side] = "7%";
    $('#'+self.posCtrlId).css(handCtrlCSS).hide();
    $('#touchspot-toggle').button()
    $('#touchspot-toggle-label').hide();
//    self.rotCtrlId = self.arm.side[0]+'rotCtrlIcon';
//    self.rotIcon = new RFH.EERotControlIcon({divId: self.posCtrlId,
//                                                 parentId: self.div,
//                                                 arm: self.arm,
//                                                 smooth: self.smooth});

    self.updateTrackHand = function (event) {
        if ( $("#"+self.arm.side[0]+"-track-hand-toggle").is(":checked") ){
            self.trackHand();
        } else {
            clearInterval(RFH.pr2.head.pubInterval);
        }
    }

    self.trackHand = function () {
        clearInterval(RFH.pr2.head.pubInterval);
        RFH.pr2.head.pubInterval = setInterval(function () {
            RFH.pr2.head.pointHead(0, 0, 0, self.arm.side[0]+'_gripper_tool_frame');
        }, 100);
    }
    $("#"+self.arm.side[0]+"-track-hand-toggle").button().on('change.rfh', self.updateTrackHand);
    $("#"+self.arm.side[0]+"-track-hand-toggle-label").hide();

    self.gripperDisplayDiv = self.arm.side[0]+'GripperDisplay';
    self.gripperDisplay = new RFH.GripperDisplay({gripper: self.gripper,
                                                   parentId: self.div,
                                                   divId: self.gripperDisplayDiv});
    var gripperCSS = {position: "absolute",
                      height: "3%",
                      width: "25%",
                      bottom: "2%"};
    gripperCSS[self.arm.side] = "3%";
    $('#'+self.gripperDisplayDiv).css( gripperCSS ).hide();

    self.start = function () {
        $("#"+self.posCtrlId + ", #touchspot-toggle-label, #"+self.arm.side[0]+"-track-hand-toggle-label").show();
        $("#"+self.gripperDisplayDiv).show();
        self.updateTrackHand();
    }
    
    self.stop = function () {
        $('#'+self.posCtrlId + ', #touchspot-toggle-label, #'+self.arm.side[0]+'-track-hand-toggle-label').hide();
        clearInterval(RFH.pr2.head.pubInterval);
        $('#'+self.gripperDisplayDiv).hide();
    };
}

RFH.EECartControlIcon = function (options) {
    'use strict';
    var self = this;
    self.divId = options.divId;
    self.parentId = options.parentId;
    self.arm = options.arm;
    self.lastDragTime = new Date();
    self.container = $('<div/>', {id: self.divId,
                                  class: "cart-ctrl-container"}).appendTo('#'+self.parentId);
    self.away = $('<div/>', {class: "away-button"}).appendTo('#'+self.divId).button();
    self.target = $('<div/>', {class: "target"}).appendTo('#'+self.divId);
    self.toward = $('<div/>', {class: "toward-button"}).appendTo('#'+self.divId).button();
    $('#'+self.divId+' .target').draggable({containment:"parent",
                                 distance: 8,
                                 revertDuration: 100,
                                 revert: true});

    self.awayCB = function (event) {
        var dx = self.smooth ? 0.005 : 0.03;
        var dt = self.smooth ? 50 : 1000;
        if ($('#'+self.divId+' .away-button').hasClass('ui-state-active')) {
            var goal = self.arm.ros.composeMsg('geometry_msgs/PoseStamped');
            goal.header.frame_id = '/torso_lift_link';
            goal.pose.position = self.arm.state.pose.position;
            goal.pose.position.x += dx;
            goal.pose.orientation = self.arm.state.pose.orientation;
            self.arm.goalPosePublisher.publish(goal);
            setTimeout(function () {self.awayCB(event)}, dt);
        } 
    }
    $('#'+self.divId+' .away-button').on('mousedown.rfh', self.awayCB);

    self.towardCB = function (event) {
        var dx = self.smooth ? 0.003 : 0.03;
        var dt = self.smooth ? 100 : 1000;
        if ($('#'+self.divId+' .toward-button').hasClass('ui-state-active')){
            var goal = self.arm.ros.composeMsg('geometry_msgs/PoseStamped');
            goal.header.frame_id = '/torso_lift_link';
            goal.pose.position = self.arm.state.pose.position;
            goal.pose.position.x -= dx;
            goal.pose.orientation = self.arm.state.pose.orientation;
            self.arm.goalPosePublisher.publish(goal);
            setTimeout(function () {self.towardCB(event)}, dt);
        }
    }
    $('#'+self.divId+' .toward-button').on('mousedown.rfh', self.towardCB);

    self.onDrag = function (event, ui) {
        var mod_del = self.smooth ? 0.005 : 0.0025;
        var dt = self.smooth ? 100 : 1000;
        clearTimeout(self.dragTimer);
        var time = new Date();
        var timeleft = time - self.lastDragTime;
        if (timeleft > 1000) {
            self.lastDragTime = time;
            var dx = -mod_del * (ui.position.left - ui.originalPosition.left);
            var dy = -mod_del * (ui.position.top - ui.originalPosition.top);
            var goal = self.arm.ros.composeMsg('geometry_msgs/PoseStamped');
            goal.header.frame_id = '/torso_lift_link';
            goal.pose.position = self.arm.state.pose.position;
            goal.pose.position.y += dx;
            goal.pose.position.z += dy;
            goal.pose.orientation = self.arm.state.pose.orientation;
            self.arm.goalPosePublisher.publish(goal);
            self.dragTimer = setTimeout(function () {self.onDrag(event, ui)}, dt);
        } else {
            self.dragTimer = setTimeout(function () {self.onDrag(event, ui)}, timeleft);
        }

    }

    self.dragStop = function (event, ui) {
        clearTimeout(self.dragTimer);
    }
    $('#'+self.divId+' .target').on('drag', self.onDrag).on('dragstop', self.dragStop);


}

RFH.EERotControlIcon = function (options) {
    'use strict';
    var self = this;
    self.divId = options.divId;
    self.parentId = options.parentId;
    self.arm = options.arm;
    self.lastDragTime = new Date();
    self.container = $('<div/>', {id: self.divId,
                                  class: "cart-ctrl-container"}).appendTo('#'+self.parentId);
    self.cwRot = $('<div/>', {class: "cw-rot"}).appendTo('#'+self.divId).button();
    self.target = $('<div/>', {class: "target-rot"}).appendTo('#'+self.divId);
    self.ccwRot = $('<div/>', {class: "ccw-rot"}).appendTo('#'+self.divId).button();
    $('#'+self.divId+' .target').draggable({containment:"parent",
                                 distance: 8,
                                 revertDuration: 100,
                                 revert: true});

    self.awayCB = function (event) {
        var dx = self.smooth ? 0.005 : 0.05;
        var dt = self.smooth ? 50 : 1000;
        if ($('#'+self.divId+' .away-button').hasClass('ui-state-active')) {
            var goal = self.arm.ros.composeMsg('geometry_msgs/PoseStamped');
            goal.header.frame_id = '/torso_lift_link';
            goal.pose.position = self.arm.state.pose.position;
            goal.pose.position.x += dx;
            goal.pose.orientation = self.arm.state.pose.orientation;
            self.arm.goalPosePublisher.publish(goal);
            setTimeout(function () {self.awayCB(event)}, dt);
        } 
    }
    $('#'+self.divId+' .away-button').on('mousedown.rfh', self.awayCB);

    self.towardCB = function (event) {
        
        var dx = self.smooth ? 0.003 : 0.05;
        var dt = self.smooth ? 100 : 1000;
        if ($('#'+self.divId+' .toward-button').hasClass('ui-state-active')){
            var goal = self.arm.ros.composeMsg('geometry_msgs/PoseStamped');
            goal.header.frame_id = '/torso_lift_link';
            goal.pose.position = self.arm.state.pose.position;
            goal.pose.position.x -= dx;
            goal.pose.orientation = self.arm.state.pose.orientation;
            self.arm.goalPosePublisher.publish(goal);
            setTimeout(function () {self.towardCB(event)}, dt);
        }
    }
    $('#'+self.divId+' .toward-button').on('mousedown.rfh', self.towardCB);

    self.onDrag = function (event, ui) {
        // x -> rot around Z
        // y -> rot around y
        var mod_del = self.smooth ? 0.005 : 0.005;
        var dt = self.smooth ? 100 : 1000;
        clearTimeout(self.dragTimer);
        var time = new Date();
        var timeleft = time - self.lastDragTime;
        if (timeleft > 1000) {
            self.lastDragTime = time;
            var dx = -mod_del * (ui.position.left - ui.originalPosition.left);
            var dy = -mod_del * (ui.position.top - ui.originalPosition.top);
            var goal = self.arm.ros.composeMsg('geometry_msgs/PoseStamped');
            goal.header.frame_id = '/torso_lift_link';
            goal.pose.position = self.arm.state.pose.position;
            goal.pose.position.y += dx;
            goal.pose.position.z += dy;
            goal.pose.orientation = self.arm.state.pose.orientation;
            self.arm.goalPosePublisher.publish(goal);
            self.dragTimer = setTimeout(function () {self.onDrag(event, ui)}, dt);
        } else {
            self.dragTimer = setTimeout(function () {self.onDrag(event, ui)}, timeleft);
        }

    }

    self.dragStop = function (event, ui) {
        clearTimeout(self.dragTimer);
    }
    $('#'+self.divId+' .target').on('drag', self.onDrag).on('dragstop', self.dragStop);

}
