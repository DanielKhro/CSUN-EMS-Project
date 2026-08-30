class BmsData {
  final double stateOfCharge;
  final double stateOfHealth;
  final double batteryVoltage;
  final double batteryCurrent;
  final double batteryTemperature;

  const BmsData({
    required this.stateOfCharge,
    required this.stateOfHealth,
    required this.batteryVoltage,
    required this.batteryCurrent,
    required this.batteryTemperature,
  });
}