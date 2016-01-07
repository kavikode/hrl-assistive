RFH.PickAndPlace = function (options) {
    'use strict';
    var self = this;
    self.ros = options.ros;
    self.arm = options.arm;
    self.gripper = options.gripper;
    self.side = self.gripper.side;
    self.name = options.name || 'pick_and_place_'+self.side;
    self.ros.getMsgDetails('hrl_task_planning/PDDLProblem');
    self.taskPublisher = new ROSLIB.Topic({
        ros: self.ros,
        name: '/perform_task',
        messageType: 'hrl_task_planning/PDDLProblem'
    });
    self.taskPublisher.advertise();

    self.ros.getMsgDetails('hrl_task_planning/PDDLState');
    self.pddlStateUpdatePub = new ROSLIB.Topic({
        ros: self.ros,
        name: '/pddl_tasks/pick_and_place_'+self.side+'/state_updates',
        messageType: '/hrl_task_planning/PDDLState'
    });
    self.pddlStateUpdatePub.advertise();
    
    self.updatePDDLState = function(pred_array){
        var msg = self.ros.composeMsg('hrl_task_planning/PDDLState');
        msg.domain = self.name;
        msg.predicates = pred_array;
        self.pddlStateUpdatePub.publish(msg);
    };

    self.getInterfaceTask = function (plan_step) {
        switch (plan_step.name){
            case 'ID-LOCATION':
                return 'idLocationTask';
            case 'FORGET-LOCATION':
                return 'LookingTask';
            case 'MOVE-ARM':
                return  self.side.substring(0,1)+'EECartTask';
            case 'GRAB':
                return self.side.substring(0,1)+'EECartTask';
            case 'RELEASE':
                return self.side.substring(0,1)+'EECartTask';
        }
    };

    self.getActionLabel = function (action) {
        var loc;
        switch (action.name){
            case 'ID-LOCATION':
                if (action.args[0].indexOf('PICK') >= 0) {
                    loc = 'Pickup';
                } else if (action.args[0].indexOf('PLACE') >= 0) {
                    loc = 'Place';
                } else {
                    loc = 'Empty';
                }
                return "Indicate %loc Location".replace('%loc', loc);
            case 'FORGET-LOCATION':
                if (action.args[0].indexOf('PICK') >= 0) {
                    loc = 'Pickup';
                } else if (action.args[0].indexOf('PLACE') >= 0) {
                    loc = 'Place';
                } else {
                    loc = 'Empty';
                }
                return "Clear Saved %loc Location".replace('%loc', loc);
            case 'MOVE-ARM':
                if (action.args[1].indexOf('PICK') >= 0) {
                    loc = 'Pickup';
                } else if (action.args[1].indexOf('PLACE') >= 0) {
                    loc = 'Place';
                } else {
                    loc = 'Empty';
                }
                return "Approach %loc Location".replace('%loc', loc);
            case "GRAB":
                return "Grab Item";
            case 'RELEASE':
                return "Set Item Down";
        }
    };

    self.setPoseToParam = function (ps_msg, location_name) {
        var poseParam = new ROSLIB.Param({
            ros: self.ros,
            name: '/pddl_tasks/'+self.name+'/KNOWN/'+location_name
        });
        poseParam.set(ps_msg);
    };

    self.sendTaskGoal = function () {
        var msg = self.ros.composeMsg('hrl_task_planning/PDDLProblem');

        msg.name = 'pick_and_place_'+self.side+'-'+ new Date().getTime().toString();
        msg.domain = 'pick_and_place_'+self.side;
        msg.init = ['(AT HAND HAND_START_LOC)', '(KNOWN HAND_START_LOC)'];  // Initialize with sensible information...
        self.setPoseToParam(self.arm.getState(), 'HAND_START_LOC');
        self.updatePDDLState(msg.init);
        if (!self.gripper.getGrasping()) {
            msg.init.push('(AT TARGET PICK_LOC)');
        }
        msg.goal = [];  // Empty goal will use default for task
        self.taskPublisher.publish(msg);
    };

    self.start = function(){};
    self.stop = function(){};
};
