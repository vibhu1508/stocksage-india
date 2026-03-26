import 'package:flutter/material.dart';

import '../../core/services/auth_service.dart';

class ProfileScreen extends StatefulWidget {
  final AuthService authService;
  final bool onboardingRequired;

  const ProfileScreen({
    super.key,
    required this.authService,
    this.onboardingRequired = false,
  });

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final _formKey = GlobalKey<FormState>();
  final _phoneCtrl = TextEditingController();
  final _addressCtrl = TextEditingController();
  final _occupationCtrl = TextEditingController();

  String _tradingExperience = 'Beginner';
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final user = widget.authService.currentUser;
    _phoneCtrl.text = user?.phone ?? '';
    _addressCtrl.text = user?.address ?? '';
    _occupationCtrl.text = user?.occupation ?? '';
    _tradingExperience = (user?.tradingExperience?.isNotEmpty ?? false)
        ? user!.tradingExperience!
        : 'Beginner';
  }

  @override
  void dispose() {
    _phoneCtrl.dispose();
    _addressCtrl.dispose();
    _occupationCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() => _saving = true);
    final ok = await widget.authService.updateProfile(
      phone: _phoneCtrl.text.trim(),
      address: _addressCtrl.text.trim(),
      occupation: _occupationCtrl.text.trim(),
      tradingExperience: _tradingExperience,
    );

    if (!mounted) return;
    setState(() => _saving = false);

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(ok
            ? (widget.onboardingRequired ? 'Profile completed' : 'Profile updated successfully')
            : 'Unable to update profile'),
      ),
    );
  }

  Future<void> _skipOnboarding() async {
    if (!widget.onboardingRequired) return;
    setState(() => _saving = true);
    final ok = await widget.authService.skipOnboarding();
    if (!mounted) return;
    setState(() => _saving = false);

    if (!ok) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Unable to skip onboarding right now')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = widget.authService.currentUser;

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.onboardingRequired ? 'Complete Your Profile' : 'Profile'),
        automaticallyImplyLeading: !widget.onboardingRequired,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (widget.onboardingRequired) ...[
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.white10),
                  ),
                  child: const Text(
                    'Please complete your onboarding details to continue.',
                    style: TextStyle(fontSize: 13),
                  ),
                ),
                const SizedBox(height: 14),
              ],
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: Colors.white10),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(user?.name ?? '', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 6),
                    const Text('Email (read-only)', style: TextStyle(fontSize: 12)),
                    const SizedBox(height: 4),
                    TextFormField(
                      enabled: false,
                      initialValue: user?.email ?? '',
                      decoration: const InputDecoration(border: OutlineInputBorder()),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _phoneCtrl,
                decoration: const InputDecoration(
                  labelText: 'Mobile Number',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _occupationCtrl,
                decoration: const InputDecoration(
                  labelText: 'Occupation',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _addressCtrl,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: 'Address',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _tradingExperience,
                items: const [
                  DropdownMenuItem(value: 'Beginner', child: Text('Beginner')),
                  DropdownMenuItem(value: 'Intermediate', child: Text('Intermediate')),
                  DropdownMenuItem(value: 'Advanced', child: Text('Advanced')),
                ],
                onChanged: (value) {
                  if (value != null) {
                    setState(() => _tradingExperience = value);
                  }
                },
                decoration: const InputDecoration(
                  labelText: 'Trading Experience',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _saving ? null : _save,
                  child: Text(_saving
                      ? 'Saving...'
                      : (widget.onboardingRequired ? 'Continue' : 'Save Changes')),
                ),
              ),
              if (widget.onboardingRequired) ...[
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: _saving ? null : _skipOnboarding,
                    child: const Text('Skip for now'),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
