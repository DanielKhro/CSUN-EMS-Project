class PredictionData {
  final double gridVoltage;
  final double gridPower;
  final double gridPowerFactor;

  final double loadPower;
  final double loadPowerFactor;

  final double predictedLoad;

  const PredictionData({
    required this.gridVoltage,
    required this.gridPower,
    required this.gridPowerFactor,
    required this.loadPower,
    required this.loadPowerFactor,
    required this.predictedLoad,
  });
}
