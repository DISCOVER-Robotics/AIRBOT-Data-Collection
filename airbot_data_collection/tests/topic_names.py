"""

MMK2/TOK(无head)/PTK(无head、spine、base):

    [Float64MultiArray]

    [[observation]]
    /left_arm/joint_state/position
    /right_arm/joint_state/position
    /left_arm_eef/joint_state/position
    /right_arm_eef/joint_state/position
    /head/joint_state/position
    /spine/joint_state/position

    [[action]]
    /left_arm_forward_position_controller/commands
    /left_arm_eef_forward_position_controller/commands

    /head_forward_position_controller/commands
    /spine_forward_position_controller/commands

    [Pose]
    [[observation]]
    /left_arm/pose/end_link
    /left_arm/pose/flange_link
    /right_arm/pose/end_link
    /right_arm/pose/flange_link

    [Pose2D]?或者直接用Pose？
    /base/pose

    [Odometry]
    /base/odom

    [Twist]
    [[action]]
    /cmd_vel

    [Image]
    /left_camera/color/image_raw
    /right_camera/color/image_raw
    /head_camera/color/image_raw
    /head_camera/aligned_depth_to_color/image_raw

    [JointState]  # 旧版tracking、mit话题名
    /left_arm_lead/joint_state
    /right_arm_lead/joint_state

Single:

    [Float64MultiArray]

    [[observation]]
    /arm/joint_state/position
    /arm/joint_state/velocity
    /arm/joint_state/effort
    /eef/joint_state/position
    /eef/joint_state/velocity
    /eef/joint_state/effort

    [JointState]

    [[action]]
    servo_node/joint_pos_cmds

    [PoseInFrame]

    [[observation]]
    /arm/pose/end_link
    /arm/pose/flange_link

    [[action]]
    servo_node/pose_target_cmds

"""
