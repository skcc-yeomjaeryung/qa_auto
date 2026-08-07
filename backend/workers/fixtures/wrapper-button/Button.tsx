export function Button(props: { onClick?: () => void; children?: React.ReactNode }) {
  return (
    <button data-testid="wrapper-button" onClick={props.onClick}>
      {props.children}
    </button>
  );
}
