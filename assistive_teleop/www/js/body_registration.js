var BodyRegistration = function (ros) {
    'use strict';
    var bodyReg = this;
    bodyReg.REG_CONFIRM_CAMERA = 'Head Registration';
    bodyReg.ros = ros;
    bodyReg.headRegCB = function () {
        $('#img_act_select').val('seedReg');
        $('#confirm_reg').button({disabled: true});
        assistive_teleop.mjpeg.setCamera(bodyReg.REG_CONFIRM_CAMERA);
        assistive_teleop.log("Click on your check to begin head registration");
    };

    bodyReg.headRegServiceClient = new bodyReg.ros.Service({
        name:'/initialize_registration',
        serviceType:'hrl_head_registration/InitializeRegistration'});

    bodyReg.registerHead = function (u,v) {
        bodyReg.headRegServiceClient.callService({u:u,v:v}, function (resp) {
            console.log('Initialize Head Registration Service Returned Success: '+resp.success);
            console.log(resp);
            $('#img_act_select').val('looking');
            if (resp.success){
                if (resp.reg_pose.pose.position.x>1.0&resp.reg_pose.pose.position.y>1.0&resp.reg_pose.pose.position.z>2.0){
                    assistive_teleop.log("Head registration insufficient, please try again");
                    console.log('Head registration insufficient');
                
                } else {
                    assistive_teleop.log('Head registration complete. Please press '"Confirm Registration"' to continue');
                    $("#confirm_reg").button({disabled: false });
                }
            }
        });
    };

    bodyReg.faceSideParam = new ros.Param({
        name: "face_side"
        });

    bodyReg.setSideParam = function () {
        var side = $("input[name=face_side]:checked").val();
        bodyReg.faceSideParam.set(side);
        console.log("Setting Param: " + bodyReg.faceSideParam.name + " = " + side);
    };

    bodyReg.regConfirmServiceClient = new bodyReg.ros.Service({
        name:"/confirm_registration",
        serviceType:"hrl_head_registration/ConfirmRegistration"
        });

    bodyReg.confirmRegistration = function () {
        bodyReg.regConfirmServiceClient.callService({}, function (resp) {
        if (resp) {
            console.log("Head Registration Confirmed.");
        }});
    };
}

var initBodyRegistration = function (tabDivId) {

    assistive_teleop.bodyReg = new BodyRegistration(assistive_teleop.ros);
    divRef = "#"+tabDivId;

    $("#tabs").on("tabsbeforeactivate", function (event, ui) {
      if (ui.newPanel.selector === divRef) {
        assistive_teleop.mjpeg.setCamera(assistive_teleop.bodyReg.REG_CONFIRM_CAMERA);
      }
    });

    $(divRef).css({"position":"relative"});
    $(divRef).append('<table id="' + tabDivId +
                     '_T0"><tr><td id="' + tabDivId + '_R0C0"></td><td id="' + tabDivId + '_R0C1"></td><td id="' + tabDivId + '_R0C2"></td><td id="' + tabDivId + '_R0C3"></td><td id="' + tabDivId + '_R0C4"></td></tr></table>');
    $(divRef+'_T0').append('<tr><td id="' + tabDivId + '_R1C0"></td></tr>')

    // Info dialog box -- Pops up with instructions for using the body registration tab
    var INFOTEXT = "The Body Registration Tab allows you to help the robot find you in the world.</br>" +
                   "To identify yourself:</br></br>"+
                   "1. Have the robot look at your face using the head camera.</br>"+
                   "2. Select the side of your face the robot can see (or which side of you the robot is currently on).</br>" +
                   "3. Select the 'Register Head' button.</br>" +
                   "4. Click on your cheek in the camera view.</br>"+
                   "5. Observe the overlaid points, showing where the robot finds your head.</br>" + 
                   "6. If the model does not line up with your face, "+
                       "try getting a better view of the face and repeat 3-5.</br>" + 
                   "7. If the model does line up with your face, click 'Confirm' to confirm that it is correct.</br>"

    $(divRef).append('<div id="'+tabDivId+'_infoDialog">' + INFOTEXT + '</div>');
    $(divRef+'_infoDialog').dialog({autoOpen:false,
                              buttons: [{text:"Ok", click:function(){$(this).dialog("close");}}],
                              modal:true,
                              title:"Body Registration Info",
                              width:"70%"
                              });

    //Info button - brings up info dialog
    $(divRef).append('<button id="'+tabDivId+'_info"> Help </button>');
    $(divRef+'_info').button();
    $(divRef+'_info').click(function () { $(divRef+'_infoDialog').dialog("open"); } );
    $(divRef+'_info').css({"position":"absolute",
                            "top":"10px",
                            "right":"10px"});

    // Register Head button - Starts registration initialization
    $(divRef+'_R0C0').append('<button class="centered" id="reg_head"> Register Head </button>');
    $("#reg_head").button();
    $("#reg_head").attr("title", "Click to initialize head registration.");
    $(divRef+'_R0C0').click(assistive_teleop.bodyReg.headRegCB);

    // Confirm Registration Button - Confirms a correct registration
    $(divRef+'_R0C1').append('<button class="centered" id="confirm_reg"> Confirm </button>');
    $("#confirm_reg").button({disabled: true });
    $("#confirm_reg").attr("title", "Click to confirm that head registration is correct.");
    $(divRef+'_R0C1').click(assistive_teleop.bodyReg.confirmRegistration);

    //Face side selector
    $(divRef+'_R1C0').append('<form id="face_side_form">' + 
                             '<input id="face_radio_left" name="face_side" type="radio" value="l">'+
                             '<label for="face_radio_left"> Left </label>' +
                             '<input id="face_radio_right" name="face_side" type="radio" value="r" checked="checked">' +
                             '<label for="face_radio_right"> Right </label>' +
                             '</form>');
    $("#face_side_form").buttonset();
    $("#face_side_form").attr("title", "Select the side of your face the robot is viewing.");
    $("#face_side_form").change(assistive_teleop.bodyReg.setSideParam);
    assistive_teleop.bodyReg.setSideParam();

}

