export default function Input({ label, error, className = '', ...props }) {
  return (
    <div className="flex flex-col gap-1 w-full">
      {label && (
        <label className="text-sm text-gray-400 font-body">{label}</label>
      )}
      <input className={`input-base ${error ? 'border-red-500' : ''} ${className}`} {...props} />
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
}
