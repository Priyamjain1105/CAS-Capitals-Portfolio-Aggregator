from flask import request, render_template, jsonify

def register_routes(app):

    @app.route('/', methods=['GET'])
    def home():
        return render_template('index.html')

    @app.route('/upload', methods=['GET'])
    def upload():
        return render_template('upload.html')

    @app.route('/dashboard', methods=['GET'])
    def dashboard():
        return render_template('dashboard.html')

    @app.route('/pyramiding', methods=['GET'])
    def pyramiding():
        return render_template('pyramiding.html')

    @app.route('/api/llm/advanced-analysis', methods=['POST'])
    def advanced_analysis():
        data = request.json or {}
        trades = data.get('trades', [])
        positions = data.get('positions', [])
        metrics = data.get('metrics', {})

        if not trades:
            return jsonify({
                'status': 'error',
                'message': 'No trade records found in the payload. Please upload a CSV first.'
            }), 400

        # Customizable system prompt
        custom_system_prompt = data.get('system_prompt')
        if not custom_system_prompt:
            custom_system_prompt = (
                "You are an expert trading psychologist and risk analyst. Analyze the following trade data "
                "for behavioral patterns, psychological flaws (like revenge trading, FOMO, over-trading, or lack of discipline), "
                "and strategic alignment. Provide a strict JSON response containing: psychological_flags, strategic_insights, "
                "and grading_and_feedback."
            )

        # Prepare payload structure for Anthropic API
        claude_payload = {
            'model': 'claude-3-5-sonnet-20241022',
            'max_tokens': 4000,
            'system': custom_system_prompt,
            'messages': [
                {
                    'role': 'user',
                    'content': f"Here are the trade log details, positions, and aggregate metrics to analyze:\n\n"
                               f"Metrics: {metrics}\n\n"
                               f"Positions: {positions[:30]}\n\n"
                               f"Raw Trade Execution Log: {trades[:100]}"
                }
            ]
        }

        # Define a structured placeholder JSON response mimicking Claude's output
        mock_claude_response = {
            'psychological_flags': [
                {
                    'flag': 'Revenge Trading Pattern',
                    'severity': 'High',
                    'description': 'Detected multiple large trades placed in quick succession immediately following a losing trade. Trade size increased by 50% on option contracts within 15 minutes of a loss.',
                    'evidence': 'Large size buy logs occurred shortly after a negative transaction occurred.'
                },
                {
                    'flag': 'Over-Trading Frequency',
                    'severity': 'Medium',
                    'description': 'Frequent short-term trades placed within short intervals, leading to ballooning transaction and brokerage fees.',
                    'evidence': 'Executed multiple micro-order lines on the same stock under identical minute windows.'
                }
            ],
            'strategic_insights': [
                {
                    'insight_type': 'Option Premium Theta Decay',
                    'description': 'High decay exposure on long options (CE/PE) held across multiple sessions.',
                    'actionable_advice': 'Avoid holding overnight naked options. Use spread strategies (such as bull call spreads or bear put spreads) to mitigate theta risk.'
                },
                {
                    'insight_type': 'Market Opening Volatility',
                    'description': 'Positions initiated in the first 15 minutes of open (09:15 - 09:30) have a win-rate of only 25%, whereas post-10:30 trades exceed 60%.',
                    'actionable_advice': 'Wait for the opening range to settle. Avoid entering positions before 10:00 AM.'
                }
            ],
            'grading_and_feedback': {
                'discipline_score': 68,
                'risk_management_score': 55,
                'consistency_score': 72,
                'overall_feedback': 'Discipline is moderately stable, but overall risk controls are deficient due to revenge scaling (increasing lot sizing after losses) and higher drawdowns. Individual loss size exceeds average wins.',
                'actionable_optimization_points': [
                    'Enforce a strict daily loss cap. Terminate trading activities once threshold is breached.',
                    'Limit active trade entry logs per asset contract to 3 per day.',
                    'Standardize position risk limits; never double transaction sizing during drawdowns.'
                ]
            }
        }

        return jsonify({
            'status': 'success',
            'message': 'Payload prepared successfully (mock response returned as external api execution is deferred).',
            'payload_prepared': claude_payload,
            'llm_analysis': mock_claude_response
        })
