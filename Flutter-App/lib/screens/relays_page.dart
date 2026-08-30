import 'package:flutter/material.dart';

import '../models/relay_data.dart';
import '../services/relay_service.dart';

class RelayPage extends StatefulWidget {
  const RelayPage({super.key});

  @override
  State<RelayPage> createState() => _RelayPageState();
}

class _RelayPageState extends State<RelayPage> {
  final RelayService _relayService = RelayService();

  late Future<RelayData> _relayDataFuture;

  bool _isChangingMode = false;

  @override
  void initState() {
    super.initState();
    _relayDataFuture = _relayService.getRelayData();
  }

  Future<void> _changeMode(int mode) async {
    setState(() {
      _isChangingMode = true;
    });

    try {
      final RelayData updatedData =
      await _relayService.setRelayMode(mode);

      if (!mounted) {
        return;
      }

      setState(() {
        _relayDataFuture = Future.value(updatedData);
      });
    } catch (error) {
      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Unable to change relay mode: $error',
          ),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isChangingMode = false;
        });
      }
    }
  }

  void _refreshData() {
    setState(() {
      _relayDataFuture = _relayService.getRelayData();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF25262C),
      appBar: AppBar(
        backgroundColor: const Color(0xFF465EAA),
        title: const Text(
          'Relay Control',
          style: TextStyle(
            fontWeight: FontWeight.bold,
          ),
        ),
        actions: [
          IconButton(
            onPressed: _refreshData,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh relay data',
          ),
        ],
      ),
      body: FutureBuilder<RelayData>(
        future: _relayDataFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState ==
              ConnectionState.waiting &&
              !snapshot.hasData) {
            return const Center(
              child: CircularProgressIndicator(),
            );
          }

          if (snapshot.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  'Unable to load relay data.\n${snapshot.error}',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: Colors.white,
                  ),
                ),
              ),
            );
          }

          if (!snapshot.hasData) {
            return const Center(
              child: Text(
                'No relay data available.',
                style: TextStyle(
                  color: Colors.white,
                ),
              ),
            );
          }

          final RelayData data = snapshot.data!;

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              CurrentModeCard(
                modeName: data.modeName,
              ),
              const SizedBox(height: 24),
              const Text(
                'Select Operating Mode',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),
              ModeButton(
                label: 'Auto',
                description:
                'The EMS automatically selects the power source.',
                icon: Icons.autorenew,
                isSelected: data.mode == 0,
                isDisabled: _isChangingMode,
                onPressed: () {
                  _changeMode(0);
                },
              ),
              const SizedBox(height: 12),
              ModeButton(
                label: 'Battery',
                description:
                'Forces the system to use battery power.',
                icon: Icons.battery_charging_full,
                isSelected: data.mode == 1,
                isDisabled: _isChangingMode,
                onPressed: () {
                  _changeMode(1);
                },
              ),
              const SizedBox(height: 12),
              ModeButton(
                label: 'Grid',
                description:
                'Forces the system to use grid power.',
                icon: Icons.electrical_services,
                isSelected: data.mode == 2,
                isDisabled: _isChangingMode,
                onPressed: () {
                  _changeMode(2);
                },
              ),
              const SizedBox(height: 24),
              const Text(
                'Relay Status',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),
              RelayStatusCard(
                label: 'Relay 1',
                isActive: data.relay1,
              ),
              const SizedBox(height: 12),
              RelayStatusCard(
                label: 'Relay 2',
                isActive: data.relay2,
              ),
              const SizedBox(height: 12),
              RelayStatusCard(
                label: 'Relay 3',
                isActive: data.relay3,
              ),
              if (_isChangingMode) ...[
                const SizedBox(height: 24),
                const Center(
                  child: CircularProgressIndicator(),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class CurrentModeCard extends StatelessWidget {
  final String modeName;

  const CurrentModeCard({
    super.key,
    required this.modeName,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF30313A),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          const Text(
            'Current Mode',
            style: TextStyle(
              color: Colors.white70,
              fontSize: 17,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            modeName,
            style: const TextStyle(
              color: Color(0xFFB9FF26),
              fontSize: 30,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }
}

class ModeButton extends StatelessWidget {
  final String label;
  final String description;
  final IconData icon;
  final bool isSelected;
  final bool isDisabled;
  final VoidCallback onPressed;

  const ModeButton({
    super.key,
    required this.label,
    required this.description,
    required this.icon,
    required this.isSelected,
    required this.isDisabled,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: isDisabled ? null : onPressed,
      style: ElevatedButton.styleFrom(
        padding: const EdgeInsets.all(16),
        backgroundColor: isSelected
            ? const Color(0xFF465EAA)
            : const Color(0xFF30313A),
        foregroundColor: Colors.white,
        alignment: Alignment.centerLeft,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
          side: BorderSide(
            color: isSelected
                ? const Color(0xFFB9FF26)
                : Colors.transparent,
            width: 2,
          ),
        ),
      ),
      child: Row(
        children: [
          Icon(
            icon,
            size: 34,
            color: isSelected
                ? const Color(0xFFB9FF26)
                : const Color(0xFF25C99A),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment:
              CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    fontSize: 19,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  description,
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
          if (isSelected)
            const Icon(
              Icons.check_circle,
              color: Color(0xFFB9FF26),
            ),
        ],
      ),
    );
  }
}

class RelayStatusCard extends StatelessWidget {
  final String label;
  final bool isActive;

  const RelayStatusCard({
    super.key,
    required this.label,
    required this.isActive,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF30313A),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(
            isActive
                ? Icons.power
                : Icons.power_off,
            size: 34,
            color: isActive
                ? const Color(0xFF25C99A)
                : Colors.redAccent,
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Text(
              label,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
              ),
            ),
          ),
          Text(
            isActive ? 'ON' : 'OFF',
            style: TextStyle(
              color: isActive
                  ? const Color(0xFFB9FF26)
                  : Colors.redAccent,
              fontSize: 19,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }
}