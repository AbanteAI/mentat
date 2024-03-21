type Props = {
    tokens_used: number;
    max_tokens: number;
    total_cost: number;
};

export default function CostOverview(props: Props) {
    return (
        <div>
            <div>
                <i>Total Cost: </i>
                <strong>${props.total_cost}</strong>
            </div>
            <div>
                <i>Tokens per prompt: </i>
                <strong>
                    {props.tokens_used} / {props.max_tokens}
                </strong>
            </div>
        </div>
    );
}
