import React from 'react';
import VideoTemplate, { VideoTemplateProps } from '../VideoTemplate';

export default function ProductShowcase(props: VideoTemplateProps) {
  return (
    <VideoTemplate
      {...props}
      introText={props.introText ?? '产品展示'}
      transition="slide"
      style={{
        ...props.style,
        primaryColor: '#FF6B35',
        fontFamily: props.style?.fontFamily ?? 'Arial Black',
      }}
    />
  );
}
