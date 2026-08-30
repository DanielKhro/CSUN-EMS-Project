class PzemData {
  // Grid Measurements
  final double gridVoltage;
  final double gridCurrent;
  final double gridPower;
  final double gridEnergy;
  final double gridFrequency;
  final double gridPowerFactor;
  final int gridAlarmStatus;

  // Load Measurements
  final double loadVoltage;
  final double loadCurrent;
  final double loadPower;
  final double loadEnergy;
  final double loadFrequency;
  final double loadPowerFactor;
  final int loadAlarmStatus;

  const PzemData({
    required this.gridVoltage,
    required this.gridCurrent,
    required this.gridPower,
    required this.gridEnergy,
    required this.gridFrequency,
    required this.gridPowerFactor,
    required this.gridAlarmStatus,

    required this.loadVoltage,
    required this.loadCurrent,
    required this.loadPower,
    required this.loadEnergy,
    required this.loadFrequency,
    required this.loadPowerFactor,
    required this.loadAlarmStatus,
  });
}